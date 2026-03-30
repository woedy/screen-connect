"""
Health check view — verifies DB and Redis connectivity.
"""
import redis
from django.db import connection
from django.http import JsonResponse
from decouple import config


def health_check(request):
    """Simple health check for Docker/load balancer probes."""
    status = {"status": "ok", "db": "ok", "redis": "ok"}
    http_status = 200

    # Check database
    try:
        connection.ensure_connection()
    except Exception as e:
        status["db"] = f"error: {e}"
        status["status"] = "degraded"
        http_status = 503

    # Check Redis
    try:
        redis_url = config("REDIS_URL", default="redis://localhost:6379/0")
        r = redis.from_url(redis_url)
        r.ping()
    except Exception as e:
        status["redis"] = f"error: {e}"
        status["status"] = "degraded"
        http_status = 503

    return JsonResponse(status, status=http_status)
