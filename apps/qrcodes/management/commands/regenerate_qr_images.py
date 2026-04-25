"""
Management command: regenerate_qr_images
=========================================
Re-generates every QR code image so the encoded URL uses the current
SITE_BASE_URL / QR_BASE_REDIRECT_URL from settings.

Run after changing SITE_BASE_URL in .env:

    python manage.py regenerate_qr_images              # all QRs
    python manage.py regenerate_qr_images --dry-run    # preview only
    python manage.py regenerate_qr_images --id <uuid>  # single QR
"""
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Regenerate QR code images with the current SITE_BASE_URL.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Print what would be updated without making changes.',
        )
        parser.add_argument(
            '--id', dest='qr_id', default=None,
            help='Regenerate a single QR by its UUID.',
        )

    def handle(self, *args, **options):
        from apps.qrcodes.models import QRCode
        from apps.qrcodes.services import generate_qr_image

        dry = options['dry_run']
        qr_id = options['qr_id']

        qs = QRCode.objects.exclude(status='archived')
        if qr_id:
            qs = qs.filter(id=qr_id)
            if not qs.exists():
                self.stderr.write(self.style.ERROR(f'QR {qr_id} not found.'))
                return

        base = getattr(settings, 'QR_BASE_REDIRECT_URL', settings.SITE_BASE_URL + '/r')
        self.stdout.write(f'Using base redirect URL: {base}')
        self.stdout.write(f'Found {qs.count()} QR code(s) to process.\n')

        ok = 0
        fail = 0
        for qr in qs.iterator():
            encoded_url = qr.short_url
            self.stdout.write(f'  [{qr.slug}] → {encoded_url}')
            if dry:
                continue
            try:
                img_url = generate_qr_image(qr)
                qr.qr_image_url = img_url
                qr.save(update_fields=['qr_image_url'])
                ok += 1
            except Exception as exc:
                self.stderr.write(self.style.WARNING(f'    FAILED: {exc}'))
                fail += 1

        if dry:
            self.stdout.write(self.style.WARNING('\n[dry-run] No changes made.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\nDone. {ok} regenerated, {fail} failed.'))
