from rest_framework import generics, permissions
from django.contrib.auth.models import User

from .serializers import UserSerializer


class UserProfileView(generics.RetrieveAPIView):
    """GET /api/auth/profile/ — returns the current authenticated user's info."""

    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user
