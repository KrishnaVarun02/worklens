import json
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def cipher():
    if not settings.FERNET_KEY:
        raise ImproperlyConfigured(
            "WORKLENS_ENCRYPTION_KEY is required before saving integration credentials"
        )
    return Fernet(settings.FERNET_KEY.encode())


def encrypt(value):
    return cipher().encrypt(json.dumps(value).encode()).decode() if value else ""


def decrypt(value):
    return json.loads(cipher().decrypt(value.encode())) if value else {}
