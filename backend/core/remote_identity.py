"""Optional trusted WSGI server identity, never a client HTTP identity header."""

from django.contrib.auth.backends import RemoteUserBackend
from django.contrib.auth.middleware import RemoteUserMiddleware
from django.core.exceptions import ImproperlyConfigured
from .permissions import audit, role


class ProvisionedRemoteUserBackend(RemoteUserBackend):
    create_unknown_user = False

    def user_can_authenticate(self, user):
        return user is not None and super().user_can_authenticate(user) and bool(role(user))


class TrustedWSGIIdentityMiddleware(RemoteUserMiddleware):
    header = "REMOTE_USER"
    async_capable = False

    def process_request(self, request):
        if hasattr(request, "scope"):
            raise ImproperlyConfigured(
                "WorkLens trusted REMOTE_USER authentication requires WSGI, not ASGI."
            )
        previous = request.user if request.user.is_authenticated else None
        super().process_request(request)
        if request.user.is_authenticated and (previous is None or previous.pk != request.user.pk):
            audit(request.user, "sso_login", "session")
