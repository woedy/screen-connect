import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


def generate_session_token():
    """Generate a cryptographically secure session token."""
    return secrets.token_urlsafe(48)


def default_expiry():
    """Return default expiry datetime based on settings."""
    hours = getattr(settings, "SESSION_DEFAULT_EXPIRY_HOURS", 2)
    return timezone.now() + timedelta(hours=hours)


class SupportSession(models.Model):
    """
    Represents a remote support session between an agent (support staff)
    and a client (end user).
    """

    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting for client"
        ACTIVE = "active", "Active"
        ENDED = "ended", "Ended"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="support_sessions",
    )
    token = models.CharField(
        max_length=128,
        default=generate_session_token,
        unique=True,
        help_text="Secure token for client to join this session",
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.WAITING,
        db_index=True,
    )
    client_connected = models.BooleanField(default=False)
    agent_connected = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(default=default_expiry)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Support Session"
        verbose_name_plural = "Support Sessions"
        indexes = [
            models.Index(fields=["created_by", "-created_at"], name="sc_session_creator_created_idx"),
            models.Index(fields=["status", "expires_at"], name="sc_session_status_exp_idx"),
        ]

    def __str__(self):
        return f"Session {self.id} ({self.status})"

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def is_active(self):
        return self.status != self.Status.ENDED and not self.is_expired

    def end_session(self):
        """Mark session as ended."""
        self.status = self.Status.ENDED
        self.ended_at = timezone.now()
        self.client_connected = False
        self.agent_connected = False
        self.save(update_fields=["status", "ended_at", "client_connected", "agent_connected"])
