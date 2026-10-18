"""Verify the delivered checker, no-clobber boundaries and static resources."""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from pathlib import Path

from certloom.artifact import bundle_members, write_bundle
from certloom.engine import VerificationError, verify_text
from certloom.producer import make_certificate
from certloom.site import build
from certloom.artifact import asset_directory

ROOT = Path(__file__).resolve().parents[1]


class ArtifactTests(unittest.TestCase):
    def test_static_site_excludes_installer_generated_bytecode(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            examples = base / "examples"
            (examples / "__pycache__").mkdir(parents=True)
            (examples / "__pycache__/source.cpython-314.pyc").write_bytes(b"cache")
            (examples / "loose.pyc").write_bytes(b"cache")
            (examples / "source.py").write_text('"""Retained source."""\n')
            with patch(
                "certloom.site.asset_directory",
                side_effect=lambda name: (
                    examples if name == "examples" else asset_directory(name)
                ),
            ):
                manifest = build(base / "site")
            paths = {row["path"] for row in manifest["files"]}
            self.assertIn("examples/source.py", paths)
            self.assertFalse(
                any("__pycache__" in p or p.endswith(".pyc") for p in paths)
            )

    def test_actual_detached_export_preserves_certificate_and_recomputes_every_claim(
        self,
    ):
        text = (ROOT / "examples/ladder64.json").read_text()
        files = bundle_members(text)
        self.assertEqual(files["certificate.json"], text.encode())
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            for name, data in files.items():
                (p / name).write_bytes(data)
            result = subprocess.run(
                [sys.executable, "-I", "-S", "checker.py", "certificate.json"],
                cwd=p,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), verify_text(text))
            document = json.loads(text)
            document["R"] = [[(0.0).hex() for _ in row] for row in document["R"]]
            (p / "certificate.json").write_text(json.dumps(document))
            result = subprocess.run(
                [sys.executable, "-I", "-S", "checker.py", "certificate.json"],
                cwd=p,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 3, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "not_certified")

    def test_invalid_input_creates_no_output_and_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "proof.zip"
            with self.assertRaises(VerificationError):
                write_bundle("{}", p)
            self.assertFalse(p.exists())
            p.write_bytes(b"unrelated existing bytes")
            with self.assertRaises(FileExistsError):
                write_bundle((ROOT / "examples/ladder64.json").read_text(), p)
            self.assertEqual(p.read_bytes(), b"unrelated existing bytes")

    def test_source_bearing_zip_and_fresh_static_build_have_exact_bytes(self):
        text = (ROOT / "examples/hilbert8.json").read_text()
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            write_bundle(text, p / "proof.zip")
            with zipfile.ZipFile(p / "proof.zip") as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(archive.read("certificate.json"), text.encode())
                self.assertEqual(
                    json.loads(archive.read("verification.json"))["result"],
                    verify_text(text),
                )
            manifest = build(p / "lab")
            self.assertEqual(
                json.loads((p / "lab/source-manifest.json").read_text()), manifest
            )
            for row in manifest["files"]:
                data = (p / "lab" / row["path"]).read_bytes()
                self.assertEqual(len(data), row["bytes"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), row["sha256"])
            for name in (
                "index.html",
                "app.mjs",
                "verify.mjs",
                "worker.mjs",
                "checker.py",
                "examples/ladder64.json",
                "docs/method.html",
            ):
                self.assertTrue((p / "lab" / name).is_file(), name)
            with self.assertRaises(FileExistsError):
                build(p / "lab")

    def test_producer_conversion_is_explicit_finite_and_dimension_bounded(self):
        document = make_certificate(
            [[2.0]], [1.0], [0.5], [[0.5]], {"index": 0, "above": 0.25}
        )
        self.assertEqual(
            verify_text(json.dumps(document))["decision"]["status"], "above"
        )
        with self.assertRaises(VerificationError):
            make_certificate([[float("nan")]], [1.0], [0.5], [[0.5]])
        with self.assertRaises(VerificationError):
            make_certificate([[True]], [1.0], [0.5], [[0.5]])
        with self.assertRaises(VerificationError):
            make_certificate([[1.0]], [1.0] * 129, [0.5], [[0.5]])


if __name__ == "__main__":
    unittest.main()
