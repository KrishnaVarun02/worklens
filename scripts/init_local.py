#!/usr/bin/env python3
"""Create ignored local secrets; never replaces existing configuration."""

import os
from pathlib import Path
import secrets
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parent.parent
example = (ROOT / ".env.example").read_text()
values = {
    "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
    "WORKLENS_ENCRYPTION_KEY": Fernet.generate_key().decode(),
    "POSTGRES_PASSWORD": secrets.token_urlsafe(32),
}
for key, value in values.items():
    example = example.replace(key + "=\n", key + "=" + value + "\n")
fd = os.open(ROOT / ".env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as handle:
    handle.write(example)
print("Created private .env. Back up the encryption key separately from your database.")
