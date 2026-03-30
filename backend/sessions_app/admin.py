from django.contrib import admin

from .models import SupportSession


@admin.register(SupportSession)
class SupportSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "created_by", "status", "client_connected", "agent_connected", "created_at", "expires_at")
    list_filter = ("status", "client_connected", "agent_connected")
    search_fields = ("id", "created_by__username")
    readonly_fields = ("id", "token", "created_at", "updated_at")
    ordering = ("-created_at",)
