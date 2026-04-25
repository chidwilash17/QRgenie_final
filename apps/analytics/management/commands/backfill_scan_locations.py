"""
Management command: backfill_scan_locations
============================================
Usage (on PythonAnywhere Bash console):
    python manage.py backfill_scan_locations
    python manage.py backfill_scan_locations --days 90
    python manage.py backfill_scan_locations --dry-run

For every ScanEvent that has ip_address set but latitude/longitude=NULL,
resolves lat/lng via ipinfo.io (HTTPS, free 50k/mo) → ipapi.co fallback
and saves it to the database.

Also fills in blank country/city fields if the API returns them.
"""
import time
import json
from urllib.request import urlopen, Request
from urllib.error import URLError
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta


_PRIVATE = (
    '127.', '10.', '192.168.',
    '172.16.', '172.17.', '172.18.', '172.19.', '172.20.',
    '172.21.', '172.22.', '172.23.', '172.24.', '172.25.',
    '172.26.', '172.27.', '172.28.', '172.29.', '172.30.',
    '172.31.', '::1',
)


def _is_private(ip: str) -> bool:
    return any(ip.startswith(p) for p in _PRIVATE)


def _resolve(ip: str) -> tuple:
    """Returns (lat, lng, city, country) or (None, None, '', '')."""
    # ipinfo.io — HTTPS, free 50k/mo, works on PythonAnywhere
    try:
        url = f"https://ipinfo.io/{ip}/json"
        req = Request(url, headers={'User-Agent': 'QRGenie/1.0', 'Accept': 'application/json'})
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        loc = data.get('loc', '')
        if loc and ',' in loc:
            parts = loc.split(',')
            return (
                float(parts[0]), float(parts[1]),
                data.get('city', ''),
                data.get('country', ''),
            )
    except Exception:
        pass

    # ipapi.co fallback
    try:
        url = f"https://ipapi.co/{ip}/json/"
        req = Request(url, headers={'User-Agent': 'QRGenie/1.0'})
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        lat = data.get('latitude') or data.get('lat')
        lng = data.get('longitude') or data.get('lon')
        if lat and lng:
            return (
                float(lat), float(lng),
                data.get('city', ''),
                data.get('country_code', ''),
            )
    except Exception:
        pass

    return (None, None, '', '')


class Command(BaseCommand):
    help = 'Backfill lat/lng (and city/country) for ScanEvents that have an IP but no coordinates.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days', type=int, default=90,
            help='Only process events from the last N days (default: 90)',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Show what would be updated without saving',
        )
        parser.add_argument(
            '--delay', type=float, default=0.2,
            help='Seconds to sleep between API calls to avoid rate limiting (default: 0.2)',
        )

    def handle(self, *args, **options):
        from apps.analytics.models import ScanEvent

        days = options['days']
        dry_run = options['dry_run']
        delay = options['delay']
        since = timezone.now() - timedelta(days=days)

        # Get distinct IPs that need resolution
        qs = (
            ScanEvent.objects
            .filter(scanned_at__gte=since, latitude__isnull=True)
            .exclude(ip_address=None)
            .exclude(ip_address='')
            .values_list('ip_address', flat=True)
            .distinct()
        )
        ips = [ip for ip in qs if not _is_private(ip)]

        self.stdout.write(f"Found {len(ips)} unique IPs needing location resolution.")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no changes will be saved."))

        resolved = 0
        failed = 0
        ip_cache: dict = {}

        for idx, ip in enumerate(ips, 1):
            if ip not in ip_cache:
                lat, lng, city, country = _resolve(ip)
                ip_cache[ip] = (lat, lng, city, country)
                time.sleep(delay)
            else:
                lat, lng, city, country = ip_cache[ip]

            if lat is None:
                self.stdout.write(self.style.WARNING(f"  [{idx}/{len(ips)}] FAILED  {ip}"))
                failed += 1
                continue

            self.stdout.write(
                self.style.SUCCESS(f"  [{idx}/{len(ips)}] OK      {ip} → ({lat:.4f}, {lng:.4f}) {city}, {country}")
            )

            if not dry_run:
                # Update all ScanEvents for this IP that still have no coords
                update_fields = {'latitude': lat, 'longitude': lng}
                events = ScanEvent.objects.filter(
                    scanned_at__gte=since,
                    ip_address=ip,
                    latitude__isnull=True,
                )
                # Also fill blank city/country
                for evt in events:
                    evt.latitude = lat
                    evt.longitude = lng
                    if not evt.city and city:
                        evt.city = city
                    if not evt.country and country:
                        evt.country = country
                    evt.save(update_fields=['latitude', 'longitude', 'city', 'country'])

            resolved += 1

        self.stdout.write("")
        self.stdout.write(f"Done. Resolved: {resolved}  Failed: {failed}")
        if dry_run:
            self.stdout.write(self.style.WARNING("(dry-run — nothing was saved)"))
