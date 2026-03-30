import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def cleanup_expired_sessions():
    """Mark expired sessions as ended."""
    from .models import SupportSession

    expired = SupportSession.objects.filter(
        expires_at__lt=timezone.now(),
    ).exclude(status=SupportSession.Status.ENDED)

    count = expired.count()
    if count > 0:
        expired.update(
            status=SupportSession.Status.ENDED,
            ended_at=timezone.now(),
            client_connected=False,
            agent_connected=False,
        )
        logger.info(f"Cleaned up {count} expired sessions")

    return count


@shared_task
def mark_inactive_sessions(inactive_minutes=30):
    """Mark sessions with no activity as ended."""
    from .models import SupportSession

    threshold = timezone.now() - timedelta(minutes=inactive_minutes)
    inactive = SupportSession.objects.filter(
        status=SupportSession.Status.WAITING,
        updated_at__lt=threshold,
    )

    count = inactive.count()
    if count > 0:
        inactive.update(
            status=SupportSession.Status.ENDED,
            ended_at=timezone.now(),
        )
        logger.info(f"Marked {count} inactive sessions as ended")

    return count
