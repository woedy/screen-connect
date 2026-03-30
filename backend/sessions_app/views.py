from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

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

    def get_queryset(self):
        return SupportSession.objects.filter(created_by=self.request.user)


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
