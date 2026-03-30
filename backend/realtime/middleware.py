"""
WebSocket authentication middleware for Django Channels.

Two connection roles:
  - role=agent  (dashboard/support staff): authenticated via JWT access token
  - role=client (Python desktop agent):    authenticated via session token
"""
import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware

logger = logging.getLogger(__name__)


@database_sync_to_async
def get_session_for_client(session_id, token):
    """Validate session token for the Python agent (role=client)."""
    from sessions_app.models import SupportSession
    try:
        session = SupportSession.objects.get(id=session_id, token=token)
        if session.is_expired or session.status == SupportSession.Status.ENDED:
            return None
        return session
    except (SupportSession.DoesNotExist, ValueError):
        return None


@database_sync_to_async
def get_session_for_agent(session_id, jwt_token):
    """Validate JWT and confirm the person is an authorized agent (support staff)."""
    from rest_framework_simplejwt.tokens import AccessToken
    from rest_framework_simplejwt.exceptions import TokenError
    from django.contrib.auth.models import User
    from sessions_app.models import SupportSession
    try:
        decoded = AccessToken(jwt_token)
        user = User.objects.get(id=decoded["user_id"])
        
        # Get the session but allow superusers OR the creator to access it
        # This fixes cases where a session is viewed by someone other than the creator
        session = SupportSession.objects.get(id=session_id)
        
        # Check authorization
        if not (user.is_superuser or user.is_staff or session.created_by == user):
            logger.warning(f"WS auth rejected: user {user.username} is not authorized for session {session_id}")
            return None

        if session.is_expired or session.status == SupportSession.Status.ENDED:
            logger.warning(f"WS auth rejected: session {session_id} is expired or ended")
            return None
            
        return session
    except TokenError as e:
        logger.warning(f"WS auth rejected: invalid JWT token: {e}")
        return None
    except (User.DoesNotExist, SupportSession.DoesNotExist, ValueError, KeyError) as e:
        logger.warning(f"WS auth rejected: {type(e).__name__}: {e}")
        return None


class TokenAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        query_string = scope.get("query_string", b"").decode("utf-8")
        params = parse_qs(query_string)

        token = params.get("token", [None])[0]
        role = params.get("role", [None])[0]

        scope["session_token"] = token
        scope["role"] = role
        scope["support_session"] = None

        if token and role in ("agent", "client"):
            path = scope.get("path", "")
            parts = path.strip("/").split("/")
            session_id = None
            for i, part in enumerate(parts):
                if part == "session" and i + 1 < len(parts):
                    session_id = parts[i + 1]
                    break

            if session_id:
                if role == "agent":
                    session = await get_session_for_agent(session_id, token)
                else:
                    session = await get_session_for_client(session_id, token)
                scope["support_session"] = session
                if not session:
                    logger.warning(f"WS auth failed: role={role} session={session_id}")

        return await super().__call__(scope, receive, send)
