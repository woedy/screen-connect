import json
import time

from django.http import StreamingHttpResponse
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from django.contrib.auth.models import User
from rest_framework.pagination import CursorPagination

from .models import SupportSession
from .serializers import (
    SessionCreateSerializer,
    SessionDetailSerializer,
    SessionListSerializer,
)


class SessionCreateView(generics.CreateAPIView):
    """POST /api/sessions/ — create a new support session."""

    serializer_class = SessionCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class SessionListView(generics.ListAPIView):
    """GET /api/sessions/ — list current user's sessions."""

    serializer_class = SessionListSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    class SessionCursorPagination(CursorPagination):
        page_size = 25
        ordering = "-created_at"

    pagination_class = SessionCursorPagination

    def get_queryset(self):
        queryset = SupportSession.objects.filter(created_by=self.request.user)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset


class SessionDetailView(generics.RetrieveAPIView):
    """GET /api/sessions/{id}/ — get session details."""

    serializer_class = SessionDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "id"

    def get_queryset(self):
        return SupportSession.objects.filter(created_by=self.request.user)


class SessionEndView(APIView):
    """POST /api/sessions/{id}/end/ — end a session."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        try:
            session = SupportSession.objects.get(id=id, created_by=request.user)
        except SupportSession.DoesNotExist:
            return Response(
                {"error": "Session not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if session.status == SupportSession.Status.ENDED:
            return Response(
                {"error": "Session already ended"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session.end_session()
        return Response(
            {"message": "Session ended", "session_id": str(session.id)},
            status=status.HTTP_200_OK,
        )


class SessionJoinView(APIView):
    """
    GET /api/sessions/{id}/join/?token=xxx
    Public endpoint — validates token and returns connection info.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, id):
        token = request.query_params.get("token")
        if not token:
            return Response(
                {"error": "Token is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            session = SupportSession.objects.get(id=id, token=token)
        except SupportSession.DoesNotExist:
            return Response(
                {"error": "Invalid session or token"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if session.is_expired:
            return Response(
                {"error": "Session has expired"},
                status=status.HTTP_410_GONE,
            )

        if session.status == SupportSession.Status.ENDED:
            return Response(
                {"error": "Session has ended"},
                status=status.HTTP_410_GONE,
            )

        if session.client_connected:
            return Response(
                {"error": "A client is already connected to this session"},
                status=status.HTTP_409_CONFLICT,
            )

        protocol = "wss" if request.is_secure() else "ws"
        ws_url = f"{protocol}://{request.get_host()}/ws/session/{session.id}/"

        return Response(
            {
                "session_id": str(session.id),
                "ws_url": ws_url,
                "token": session.token,
                "status": session.status,
            },
            status=status.HTTP_200_OK,
        )


class SessionStreamView(APIView):
    """
    GET /api/sessions/stream/?token=<access_token>
    Server-Sent Events stream for dashboard session updates.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        token = request.query_params.get("token")
        if not token:
            return Response({"error": "Token is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            decoded = AccessToken(token)
            user = User.objects.get(id=decoded["user_id"])
        except (TokenError, User.DoesNotExist, KeyError, ValueError):
            return Response({"error": "Invalid token"}, status=status.HTTP_401_UNAUTHORIZED)

        def event_stream():
            last_payload = None
            while True:
                rows = list(
                    SupportSession.objects.filter(created_by=user)
                    .values(
                        "id", "status", "client_connected", "agent_connected",
                        "created_at", "expires_at", "ended_at", "token"
                    )
                    .order_by("-created_at")[:100]
                )
                payload = json.dumps(rows, default=str)
                if payload != last_payload:
                    yield f"event: sessions\ndata: {payload}\n\n"
                    last_payload = payload
                yield "event: heartbeat\ndata: ok\n\n"
                time.sleep(3)

        response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
