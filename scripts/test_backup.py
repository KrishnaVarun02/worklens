import io
import os
from pathlib import Path
import tempfile
import unittest
from cryptography.exceptions import InvalidTag
from backup import atomic_transform, decrypt, encrypt


class BackupTests(unittest.TestCase):
    def test_large_roundtrip(self):
        plain = os.urandom(2_100_001)
        key = os.urandom(32)
        encrypted = io.BytesIO()
        encrypt(io.BytesIO(plain), encrypted, key)
        encrypted.seek(0)
        restored = io.BytesIO()
        decrypt(encrypted, restored, key)
        self.assertEqual(restored.getvalue(), plain)

    def test_tamper_and_wrong_key_do_not_publish_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = os.urandom(32)
            (root / "source").write_bytes(b"synthetic employee data")
            atomic_transform(root / "source", root / "backup", key, encrypt)
            with self.assertRaises(InvalidTag):
                atomic_transform(root / "backup", root / "restored", os.urandom(32), decrypt)
            self.assertFalse((root / "restored").exists())
            body = bytearray((root / "backup").read_bytes())
            body[-18] ^= 1
            (root / "backup").write_bytes(body)
            with self.assertRaises(InvalidTag):
                atomic_transform(root / "backup", root / "restored", key, decrypt)
            self.assertFalse((root / "restored").exists())
            self.assertFalse(list(root.glob(".worklens-*")))

    def test_truncation_and_existing_output(self):
        with self.assertRaises(ValueError):
            decrypt(io.BytesIO(b"wrong"), io.BytesIO(), os.urandom(32))
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "existing"
            file.write_bytes(b"preserve")
            with self.assertRaises(ValueError):
                atomic_transform(file, file, os.urandom(32), encrypt)
            self.assertEqual(file.read_bytes(), b"preserve")


if __name__ == "__main__":
    unittest.main()
