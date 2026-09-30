from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from core.models import Employee

BACKENDS = [
    "core.remote_identity.ProvisionedRemoteUserBackend",
    "django.contrib.auth.backends.ModelBackend",
]
MIDDLEWARE = list(settings.MIDDLEWARE)
POSITION = MIDDLEWARE.index("django.contrib.auth.middleware.AuthenticationMiddleware") + 1
MIDDLEWARE.insert(POSITION, "core.remote_identity.TrustedWSGIIdentityMiddleware")


@override_settings(AUTHENTICATION_BACKENDS=BACKENDS, MIDDLEWARE=MIDDLEWARE)
class RemoteIdentityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="provisioned-person", password="synthetic-passphrase-2026"
        )
        self.employee = Employee.objects.create(
            user=self.user,
            stable_id="sso-synthetic",
            name="Synthetic Person",
            email="person@example.test",
        )

    def test_trusted_wsgi_identity_uses_preprovisioned_account(self):
        response = self.client.get("/api/auth/session/", REMOTE_USER=self.user.username)
        self.assertEqual(response.json()["user"]["id"], self.user.pk)
        # Upstream removal ends the remote-authenticated session.
        self.assertIsNone(self.client.get("/api/auth/session/").json()["user"])

    def test_http_identity_header_cannot_authenticate(self):
        response = self.client.get(
            "/api/auth/session/",
            HTTP_REMOTE_USER=self.user.username,
            HTTP_X_AUTH_USER=self.user.username,
        )
        self.assertIsNone(response.json()["user"])

    def test_unknown_and_offboarded_people_cannot_authenticate(self):
        self.assertIsNone(
            self.client.get("/api/auth/session/", REMOTE_USER="unknown-person").json()["user"]
        )
        self.assertFalse(get_user_model().objects.filter(username="unknown-person").exists())
        self.employee.active = False
        self.employee.save()
        self.assertIsNone(
            self.client.get("/api/auth/session/", REMOTE_USER=self.user.username).json()["user"]
        )
