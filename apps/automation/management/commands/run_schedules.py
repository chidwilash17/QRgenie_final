"""
Management command to process due QR schedules.
Run via cron every minute: python manage.py run_schedules
"""
from django.core.management.base import BaseCommand
from apps.automation.schedule_engine import process_due_schedules


class Command(BaseCommand):
    help = 'Process all due QR schedules'

    def handle(self, *args, **options):
        count = process_due_schedules()
        self.stdout.write(self.style.SUCCESS(f'Processed {count} schedule(s)'))
