from django.urls import re_path

from .consumers import ScreenShareConsumer

websocket_urlpatterns = [
    re_path(r"ws/session/(?P<session_id>[0-9a-f\-]+)/$", ScreenShareConsumer.as_asgi()),
]
