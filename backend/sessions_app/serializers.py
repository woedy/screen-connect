from rest_framework import serializers

from .models import SupportSession


class SessionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new support session."""

    join_url = serializers.SerializerMethodField()

    class Meta:
        model = SupportSession
        fields = ("id", "token", "status", "created_at", "expires_at", "join_url")
        read_only_fields = ("id", "token", "status", "created_at", "expires_at", "join_url")

    def get_join_url(self, obj):
        request = self.context.get("request")
        if request:
            return f"{request.scheme}://{request.get_host()}/join/{obj.id}"
        return f"/join/{obj.id}"

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)


class SessionListSerializer(serializers.ModelSerializer):
    """Serializer for listing sessions."""

    created_by_username = serializers.CharField(source="created_by.username", read_only=True)
    join_url = serializers.SerializerMethodField()
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = SupportSession
        fields = (
            "id",
            "created_by_username",
            "token",
            "status",
            "client_connected",
            "agent_connected",
            "created_at",
            "expires_at",
            "ended_at",
            "join_url",
            "is_expired",
        )
        read_only_fields = fields

    def get_join_url(self, obj):
        request = self.context.get("request")
        if request:
            return f"{request.scheme}://{request.get_host()}/join/{obj.id}"
        return f"/join/{obj.id}"


class SessionDetailSerializer(SessionListSerializer):
    """Detailed session serializer with connection info."""

    ws_url = serializers.SerializerMethodField()

    class Meta(SessionListSerializer.Meta):
        fields = SessionListSerializer.Meta.fields + ("ws_url",)

    def get_ws_url(self, obj):
        request = self.context.get("request")
        if request:
            protocol = "wss" if request.is_secure() else "ws"
            return f"{protocol}://{request.get_host()}/ws/session/{obj.id}/"
        return f"/ws/session/{obj.id}/"


class SessionJoinSerializer(serializers.Serializer):
    """Serializer for the public join endpoint response."""

    session_id = serializers.UUIDField()
    ws_url = serializers.CharField()
    token = serializers.CharField()
    status = serializers.CharField()
