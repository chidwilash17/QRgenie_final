"""
QR Codes Celery Tasks
======================
"""
from celery import shared_task
import logging

logger = logging.getLogger('apps.qrcodes')


@shared_task(name='qrcodes.process_bulk_upload')
def process_bulk_upload_task(job_id: str):
    """Async task for processing bulk Excel uploads."""
    from .services import process_bulk_upload
    logger.info(f"Starting bulk upload job: {job_id}")
    process_bulk_upload(job_id)
    logger.info(f"Completed bulk upload job: {job_id}")
