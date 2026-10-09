"""Offline encrypted workspace backup and restore regressions.

Only isolated temporary workspaces are used; no real user data is read/written.
"""
import io
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core import access_control as auth
from core import workspace_backup as backup

PASSWORD = "long-unpredictable-offline-passphrase"


class WorkspaceBackupTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        for p in (
            patch.object(auth, "AUTH_DB_PATH", self.root / "auth.sqlite3"),
            patch.object(auth, "WORKSPACE_ROOT", self.root / "workspaces"),
            patch.dict(os.environ, {"AJAN_HALI_AUTH_MODE": "workspace"}),
        ):
            p.start()
            self.addCleanup(p.stop)
        auth.create_workspace("firm_alpha", "Firm Alpha")
        auth.create_workspace("firm_beta", "Firm Beta")
        self.alpha = auth.WORKSPACE_ROOT / "firm_alpha"
        job = self.alpha / "jobs" / "JOB-SAME"
        job.mkdir(parents=True)
        (self.alpha / "factory_settings.json").write_text('{"company_name":"Alpha"}', encoding="utf-8")
        (self.alpha / "supplier_catalog.json").write_text('{"products":[],"colors":[]}', encoding="utf-8")
        (job / "analysis_report.json").write_bytes(b'{"job_id":"JOB-SAME","source":"alpha"}')
        (job / "00_input.png").write_bytes(b"alpha-photo\x00data")
        evidence = job / "evidence"
        evidence.mkdir()
        (evidence / "original.blob").write_bytes(b"unverified physical sample")
        with sqlite3.connect(job / "studio.sqlite3") as db:
            db.execute("CREATE TABLE revisions (id INTEGER PRIMARY KEY, kind TEXT)")
            db.execute("INSERT INTO revisions (kind) VALUES ('DRAFT')")

    def test_encrypted_backup_and_restore_without_overwrite(self):
        destination = self.root / "alpha.ahb"
        backup.backup_to_file("firm_alpha", destination, PASSWORD)
        blob = destination.read_bytes()
        self.assertTrue(blob.startswith(backup.MAGIC))
        self.assertNotIn(b"Alpha", blob)
        self.assertNotIn(b"alpha-photo", blob)
        self.assertNotIn(b"unverified physical sample", blob)
        with self.assertRaises(FileExistsError):
            backup.backup_to_file("firm_alpha", destination, PASSWORD)
        with self.assertRaises(FileExistsError):
            backup.restore_new_workspace("firm_alpha", destination, PASSWORD)
        shutil.rmtree(self.alpha)
        restored = backup.restore_new_workspace("firm_alpha", destination, PASSWORD)
        self.assertEqual((restored / "factory_settings.json").read_text(),
                         '{"company_name":"Alpha"}')
        self.assertEqual((restored / "jobs/JOB-SAME/00_input.png").read_bytes(),
                         b"alpha-photo\x00data")
        self.assertEqual((restored / "jobs/JOB-SAME/evidence/original.blob").read_bytes(),
                         b"unverified physical sample")
        with sqlite3.connect(restored / "jobs/JOB-SAME/studio.sqlite3") as db:
            self.assertEqual(db.execute("SELECT kind FROM revisions").fetchone()[0], "DRAFT")
        self.assertTrue(auth.AUTH_DB_PATH.exists())

    def test_wrong_passphrase_and_changed_ciphertext_fail_closed(self):
        target = self.root / "alpha.ahb"
        backup.backup_to_file("firm_alpha", target, PASSWORD)
        shutil.rmtree(self.alpha)
        with self.assertRaisesRegex(ValueError, "Wrong passphrase"):
            backup.restore_new_workspace("firm_alpha", target, "wrong-passphrase-12345")
        self.assertFalse(self.alpha.exists())
        tampered = self.root / "tampered.ahb"
        blob = bytearray(target.read_bytes())
        blob[-1] ^= 0x01
        tampered.write_bytes(blob)
        with self.assertRaisesRegex(ValueError, "tampered backup"):
            backup.restore_new_workspace("firm_alpha", tampered, PASSWORD)
        self.assertFalse(self.alpha.exists())
        truncated = self.root / "truncated.ahb"
        truncated.write_bytes(blob[:20])
        with self.assertRaisesRegex(ValueError, "Unrecognized"):
            backup.restore_new_workspace("firm_alpha", truncated, PASSWORD)
        self.assertFalse(self.alpha.exists())

    def test_cannot_restore_into_another_company(self):
        target = self.root / "alpha.ahb"
        backup.backup_to_file("firm_alpha", target, PASSWORD)
        beta = auth.WORKSPACE_ROOT / "firm_beta"
        with self.assertRaisesRegex(ValueError, "different workspace"):
            backup.restore_new_workspace("firm_beta", target, PASSWORD)
        self.assertFalse(beta.exists())

    def test_no_symlinks_and_no_data_inside_live_workspace_destination(self):
        with self.assertRaises(ValueError):
            backup.backup_to_file("firm_alpha",
                self.alpha / "leaked.ahb", PASSWORD)
        with self.assertRaises(ValueError):
            backup.build_encrypted_snapshot("firm_alpha", "short")
        external = self.root / "elsewhere.txt"
        external.write_text("external")
        link = self.alpha / "jobs/JOB-SAME/linked.txt"
        try:
            link.symlink_to(external)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink unsupported on this OS")
        with self.assertRaisesRegex(ValueError, "Symlinks"):
            backup.build_encrypted_snapshot("firm_alpha", PASSWORD)
        link.unlink()

    def encrypt_test_archive(self, manifest, files):
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json", json.dumps(manifest))
            for path, payload in files.items():
                z.writestr("data/" + path, payload)
        salt, nonce = bytes(range(16)), bytes(range(12))
        payload = AESGCM(backup._derive(PASSWORD, salt)).encrypt(
            nonce, raw.getvalue(), backup.AAD)
        return backup.MAGIC + salt + nonce + payload

    def test_traversal_and_unlisted_files_rejected_even_if_encrypted(self):
        import hashlib
        for key in ("../escape.txt", "jobs/../../escape.txt", "C:\\Windows\\temp"):
            with self.subTest(path=key):
                data = b"x"
                manifest = {"schema": backup.SCHEMA, "workspace_id": "firm_beta",
                    "files": [{"name": key, "size": len(data),
                               "sha256": hashlib.sha256(data).hexdigest()}]}
                malicious = self.root / "malicious.ahb"
                malicious.write_bytes(self.encrypt_test_archive(manifest, {key: data}))
                with self.assertRaises(ValueError):
                    backup.restore_new_workspace("firm_beta", malicious, PASSWORD)
                self.assertFalse((auth.WORKSPACE_ROOT / "firm_beta").exists())
        proper = "factory_settings.json"
        payload = b"{}"
        manifest = {"schema": backup.SCHEMA, "workspace_id": "firm_beta",
            "files": [{"name": proper, "size": len(payload),
                       "sha256": hashlib.sha256(payload).hexdigest()}]}
        rogue = self.root / "extra.ahb"
        rogue.write_bytes(self.encrypt_test_archive(manifest, {
            proper: payload, "jobs/JOB-DATA/secret.txt": b"surprise",
        }))
        with self.assertRaisesRegex(ValueError, "unlisted"):
            backup.restore_new_workspace("firm_beta", rogue, PASSWORD)
        self.assertFalse((auth.WORKSPACE_ROOT / "firm_beta").exists())

    def test_corrupt_sqlite_does_not_install_partial_restore(self):
        import hashlib
        file = "jobs/JOB-TEST/studio.sqlite3"
        payload = b"not a sqlite database"
        manifest = {"schema": backup.SCHEMA, "workspace_id": "firm_beta",
            "files": [{"name": file, "size": len(payload),
                       "sha256": hashlib.sha256(payload).hexdigest()}]}
        bad = self.root / "sqlite-corrupt.ahb"
        bad.write_bytes(self.encrypt_test_archive(manifest, {file: payload}))
        with self.assertRaises(sqlite3.DatabaseError):
            backup.restore_new_workspace("firm_beta", bad, PASSWORD)
        self.assertFalse((auth.WORKSPACE_ROOT / "firm_beta").exists())


if __name__ == "__main__":
    unittest.main()
