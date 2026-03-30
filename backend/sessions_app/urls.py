from django.urls import path

from .views import (
    SessionCreateView,
    SessionDetailView,
    SessionEndView,
    SessionJoinView,
    SessionListView,
)

urlpatterns = [
    path("", SessionCreateView.as_view(), name="session_create"),
    path("list/", SessionListView.as_view(), name="session_list"),
    path("<uuid:id>/", SessionDetailView.as_view(), name="session_detail"),
    path("<uuid:id>/end/", SessionEndView.as_view(), name="session_end"),
    path("<uuid:id>/join/", SessionJoinView.as_view(), name="session_join"),
]
