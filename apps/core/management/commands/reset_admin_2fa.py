from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = 'Reset 2FA for an admin user (use if they lost their authenticator)'

    def add_arguments(self, parser):
        parser.add_argument('email', type=str, help='Email of the admin user')

    def handle(self, *args, **options):
        User = get_user_model()
        try:
            user = User.objects.get(email=options['email'])
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'No user found with email: {options["email"]}'))
            return

        if not user.is_staff:
            self.stderr.write(self.style.WARNING(f'{user.email} is not a staff user.'))

        user.totp_secret = ''
        user.is_2fa_enabled = False
        user.email_otp_code = ''
        user.email_otp_expires = None
        user.save(update_fields=['totp_secret', 'is_2fa_enabled', 'email_otp_code', 'email_otp_expires'])
        self.stdout.write(self.style.SUCCESS(f'2FA reset for {user.email}. They will be prompted to set up 2FA again.'))
