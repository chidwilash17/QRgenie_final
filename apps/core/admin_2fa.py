"""
Admin 2FA — Setup & Verification Views
========================================
Two-factor authentication for Django admin using TOTP (Google Authenticator)
with email-based initial setup verification.
"""
import hashlib
import io
import base64
import logging
import secrets
from datetime import timedelta

import pyotp
import qrcode
from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.cache import cache
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

logger = logging.getLogger('qrgenie')


# ── Helpers ──────────────────────────────────────────────

def _hash_otp(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def send_email_otp(user):
    code = f"{secrets.randbelow(1000000):06d}"
    user.email_otp_code = _hash_otp(code)
    user.email_otp_expires = timezone.now() + timedelta(minutes=5)
    user.save(update_fields=['email_otp_code', 'email_otp_expires'])

    send_mail(
        subject='QRGenie Admin — Email Verification Code',
        message=f'Your verification code is: {code}\n\nThis code expires in 5 minutes.',
        html_message=(
            '<div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:32px;">'
            '<h2 style="color:#1a1a2e;">QRGenie Admin Verification</h2>'
            '<p>Your verification code is:</p>'
            f'<h1 style="letter-spacing:8px;font-family:monospace;font-size:36px;'
            f'color:#6366f1;background:#f5f3ff;padding:16px 24px;border-radius:12px;'
            f'text-align:center;">{code}</h1>'
            '<p style="color:#666;">This code expires in <strong>5 minutes</strong>.</p>'
            '<p style="color:#999;font-size:12px;margin-top:24px;">If you did not request this, ignore this email.</p>'
            '</div>'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )


def verify_email_otp(user, code: str) -> bool:
    if not user.email_otp_code or not user.email_otp_expires:
        return False
    if timezone.now() > user.email_otp_expires:
        return False
    return _hash_otp(code.strip()) == user.email_otp_code


def generate_totp_qr_base64(user, secret: str) -> str:
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=user.email, issuer_name='QRGenie Admin')
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()


def verify_totp(secret: str, code: str) -> bool:
    totp = pyotp.TOTP(secret)
    return totp.verify(code.strip(), valid_window=1)


def _check_rate_limit(user_pk, action='verify'):
    cache_key = f"2fa_{action}_attempts:{user_pk}"
    attempts = cache.get(cache_key, 0)
    if attempts >= 5:
        return False  # locked out
    return True


def _record_failed_attempt(user_pk, action='verify'):
    cache_key = f"2fa_{action}_attempts:{user_pk}"
    attempts = cache.get(cache_key, 0)
    cache.set(cache_key, attempts + 1, timeout=900)  # 15 min lockout


def _clear_attempts(user_pk, action='verify'):
    cache.delete(f"2fa_{action}_attempts:{user_pk}")


# ── Setup View (multi-step) ─────────────────────────────

@staff_member_required
@require_http_methods(["GET", "POST"])
def admin_2fa_setup_view(request):
    user = request.user

    if user.is_2fa_enabled:
        return redirect('admin-2fa-verify')

    step = request.session.get('admin_2fa_setup_step', 1)

    if step == 1:
        if request.method == 'GET':
            try:
                send_email_otp(user)
                messages.info(request, f'A verification code has been sent to {user.email}')
            except Exception as e:
                logger.error(f'[2FA] Email send failed: {e}')
                messages.error(request, 'Failed to send verification email. Check email settings.')
            return render(request, 'admin/2fa_setup_email.html', {'email': user.email})

        # POST — verify email code
        if not _check_rate_limit(user.pk, 'email'):
            messages.error(request, 'Too many failed attempts. Please wait 15 minutes.')
            return render(request, 'admin/2fa_setup_email.html', {'email': user.email})

        code = request.POST.get('code', '')
        if verify_email_otp(user, code):
            _clear_attempts(user.pk, 'email')
            secret = pyotp.random_base32()
            request.session['pending_totp_secret'] = secret
            request.session['admin_2fa_setup_step'] = 2
            return redirect('admin-2fa-setup')
        else:
            _record_failed_attempt(user.pk, 'email')
            messages.error(request, 'Invalid or expired code. A new code has been sent.')
            try:
                send_email_otp(user)
            except Exception:
                pass
            return render(request, 'admin/2fa_setup_email.html', {'email': user.email})

    elif step == 2:
        secret = request.session.get('pending_totp_secret', '')
        if not secret:
            request.session['admin_2fa_setup_step'] = 1
            return redirect('admin-2fa-setup')

        if request.method == 'GET':
            qr_base64 = generate_totp_qr_base64(user, secret)
            return render(request, 'admin/2fa_setup_qr.html', {
                'qr_base64': qr_base64,
                'secret': secret,
            })

        # POST — verify TOTP code
        if not _check_rate_limit(user.pk, 'totp_setup'):
            messages.error(request, 'Too many failed attempts. Please wait 15 minutes.')
            qr_base64 = generate_totp_qr_base64(user, secret)
            return render(request, 'admin/2fa_setup_qr.html', {
                'qr_base64': qr_base64, 'secret': secret,
            })

        code = request.POST.get('code', '')
        if verify_totp(secret, code):
            _clear_attempts(user.pk, 'totp_setup')
            user.totp_secret = secret
            user.is_2fa_enabled = True
            user.email_otp_code = ''
            user.email_otp_expires = None
            user.save(update_fields=[
                'totp_secret', 'is_2fa_enabled',
                'email_otp_code', 'email_otp_expires',
            ])
            request.session['admin_2fa_verified'] = True
            request.session.pop('pending_totp_secret', None)
            request.session.pop('admin_2fa_setup_step', None)
            messages.success(request, '2FA has been successfully enabled!')
            return redirect('admin:index')
        else:
            _record_failed_attempt(user.pk, 'totp_setup')
            messages.error(request, 'Invalid code. Please try again.')
            qr_base64 = generate_totp_qr_base64(user, secret)
            return render(request, 'admin/2fa_setup_qr.html', {
                'qr_base64': qr_base64, 'secret': secret,
            })

    # Unknown step — reset
    request.session['admin_2fa_setup_step'] = 1
    return redirect('admin-2fa-setup')


# ── Verify View ──────────────────────────────────────────

@staff_member_required
@require_http_methods(["GET", "POST"])
def admin_2fa_verify_view(request):
    user = request.user

    if not user.is_2fa_enabled:
        return redirect('admin-2fa-setup')

    if request.session.get('admin_2fa_verified'):
        return redirect('admin:index')

    if request.method == 'GET':
        return render(request, 'admin/2fa_verify.html')

    # POST — verify TOTP
    if not _check_rate_limit(user.pk):
        messages.error(request, 'Too many failed attempts. Please wait 15 minutes.')
        return render(request, 'admin/2fa_verify.html')

    code = request.POST.get('code', '')
    if verify_totp(user.totp_secret, code):
        _clear_attempts(user.pk)
        request.session['admin_2fa_verified'] = True
        messages.success(request, 'Identity verified.')
        return redirect('admin:index')
    else:
        _record_failed_attempt(user.pk)
        messages.error(request, 'Invalid code. Please try again.')
        return render(request, 'admin/2fa_verify.html')
