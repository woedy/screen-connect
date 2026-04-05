from django.urls import path

from .views import (
    SessionCreateView,
    SessionDetailView,
    SessionEndView,
    SessionJoinView,
    SessionListView,
    SessionStreamView,
    AgentBootstrapView,
    SessionRestartView,
)

urlpatterns = [
    path("", SessionCreateView.as_view(), name="session_create"),
    path("list/", SessionListView.as_view(), name="session_list"),
    path("stream/", SessionStreamView.as_view(), name="session_stream"),
    path("<uuid:id>/", SessionDetailView.as_view(), name="session_detail"),
    path("<uuid:id>/end/", SessionEndView.as_view(), name="session_end"),
    path("<uuid:id>/restart/", SessionRestartView.as_view(), name="session_restart"),
    path("<uuid:id>/join/", SessionJoinView.as_view(), name="session_join"),
    path("agent/bootstrap/", AgentBootstrapView.as_view(), name="agent_bootstrap"),
]
