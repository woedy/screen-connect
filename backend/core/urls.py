"""
Root URL configuration.
"""
from django.contrib import admin
from django.urls import include, path
from core.health import health_check

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/sessions/", include("sessions_app.urls")),
    path("health/", health_check, name="health_check"),
]

