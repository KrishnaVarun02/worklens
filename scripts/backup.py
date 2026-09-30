#!/usr/bin/env python3
"""Authenticated streaming backup envelopes. Keys never travel inside a backup."""

import argparse
import base64
import os
from pathlib import Path
import subprocess
import tempfile

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC = b"WORKLENS-BACKUP-v1\n"
CHUNK = 1024 * 1024


def load_key(path):
    key = base64.urlsafe_b64decode(Path(path).read_bytes().strip())
    if len(key) != 32:
        raise ValueError("Backup key must contain 32 random bytes, URL-safe base64 encoded.")
    return key


def encrypt(source, target, key):
    nonce = os.urandom(12)
    cipher = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    cipher.authenticate_additional_data(MAGIC)
    target.write(MAGIC + nonce)
    while chunk := source.read(CHUNK):
        target.write(cipher.update(chunk))
    target.write(cipher.finalize())
    target.write(cipher.tag)


def decrypt(source, target, key):
    # Caller must keep output private until authentication succeeds.
    if source.read(len(MAGIC)) != MAGIC:
        raise ValueError("Not a supported WorkLens backup.")
    nonce = source.read(12)
    start = source.tell()
    source.seek(0, 2)
    end = source.tell() - 16
    if end < start:
        raise ValueError("Truncated backup.")
    source.seek(end)
    tag = source.read(16)
    source.seek(start)
    cipher = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
    cipher.authenticate_additional_data(MAGIC)
    left = end - start
    while left:
        chunk = source.read(min(CHUNK, left))
        if not chunk:
            raise ValueError("Truncated backup.")
        target.write(cipher.update(chunk))
        left -= len(chunk)
    target.write(cipher.finalize())


def atomic_transform(input_path, output_path, key, operation):
    output = Path(output_path)
    if output.exists():
        raise ValueError("Refusing to replace an existing output.")
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".worklens-", dir=output.parent)
    try:
        with os.fdopen(fd, "wb") as target, open(input_path, "rb") as source:
            operation(source, target, key)
            target.flush()
            os.fsync(target.fileno())
        # Atomic no-clobber publication, after authentication on decrypt.
        os.link(temp, output)
    finally:
        os.unlink(temp)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["keygen", "encrypt", "decrypt", "create", "restore"])
    parser.add_argument("--key-file", required=True)
    parser.add_argument("--input")
    parser.add_argument("--output")
    parser.add_argument(
        "--confirm-database", help="Exact PGDATABASE to restore into an EMPTY database."
    )
    args = parser.parse_args()
    if args.action == "keygen":
        fd = os.open(args.key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(base64.urlsafe_b64encode(os.urandom(32)) + b"\n")
        return
    key = load_key(args.key_file)
    if args.action in ("encrypt", "decrypt"):
        if not args.input or not args.output:
            parser.error("--input and --output are required")
        atomic_transform(
            args.input, args.output, key, encrypt if args.action == "encrypt" else decrypt
        )
    elif args.action == "create":
        if not args.output:
            parser.error("--output is required")
        output = Path(args.output)
        if output.exists():
            parser.error("Output already exists")
        output.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix=".worklens-", dir=output.parent)
        try:
            # libpq environment supplies the credential; no password command argument.
            process = subprocess.Popen(
                ["pg_dump", "--format=custom", "--no-owner"], stdout=subprocess.PIPE
            )
            with os.fdopen(fd, "wb") as target:
                encrypt(process.stdout, target, key)
                target.flush()
                os.fsync(target.fileno())
            if process.wait() != 0:
                raise RuntimeError("pg_dump failed; no backup published.")
            os.link(temp, output)
        finally:
            os.unlink(temp)
    elif args.action == "restore":
        database = os.environ.get("PGDATABASE", "")
        if not args.input or not database or args.confirm_database != database:
            parser.error("--input and --confirm-database matching PGDATABASE are required")
        # Verify fully BEFORE supplying any bytes to pg_restore. Temporary data needs
        # an encrypted filesystem/TMPDIR; default production guidance uses tmpfs.
        with tempfile.TemporaryFile() as plain, open(args.input, "rb") as source:
            decrypt(source, plain, key)
            plain.seek(0)
            subprocess.run(
                [
                    "pg_restore",
                    "--single-transaction",
                    "--exit-on-error",
                    "--no-owner",
                    "--no-acl",
                    "--dbname",
                    database,
                ],
                stdin=plain,
                check=True,
            )


if __name__ == "__main__":
    main()
