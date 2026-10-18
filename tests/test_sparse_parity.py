"""Captured NIST data: independent Fraction oracle and recipient handoff."""

import json
from fractions import Fraction as F
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from certloom.engine import verify_text
from certloom.artifact import write_bundle
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NAMES = (
    "fipy-transient400",
    "fipy-steady400",
    "fipy-uniform-refusal",
    "fipy-altered-answer",
)


def fraction(record):
    return F(int(record["numerator"]), int(record["denominator"]))


def oracle(doc):
    A = doc["A"]
    w = list(map(lambda s: F(float.fromhex(s)), doc["weights"]))
    x = [F(float.fromhex(s)) for s in doc["x"]]
    b = [F(float.fromhex(s)) for s in doc["b"]]
    gaps = []
    residuals = []
    for i in range(len(b)):
        row = {
            A["indices"][k]: F(float.fromhex(A["data"][k]))
            for k in range(A["indptr"][i], A["indptr"][i + 1])
        }
        gaps.append(
            abs(row.get(i, F(0))) * w[i]
            - sum(abs(v) * w[j] for j, v in row.items() if j != i)
        )
        residuals.append(abs(b[i] - sum(v * x[j] for j, v in row.items())))
    if min(gaps) <= 0:
        return min(gaps), None, None
    tau = max(r / g for r, g in zip(residuals, gaps))
    return min(gaps), tau, [(v - wi * tau, v + wi * tau) for v, wi in zip(x, w)]


class SparseHandoffTests(unittest.TestCase):
    def test_all_captured_components_and_exact_cross_engine_parity(self):
        texts = [(ROOT / "examples" / (n + ".json")).read_text() for n in NAMES]
        expected = []
        for name, text in zip(NAMES, texts):
            with self.subTest(name=name):
                doc = json.loads(text)
                result = verify_text(text)
                expected.append(result)
                gap, tau, bounds = oracle(doc)
                self.assertEqual(result["dimension"], 400)
                self.assertEqual(result["nonzeros"], 1920)
                self.assertEqual(fraction(result["minimum_gap"]), gap)
                if bounds is None:
                    self.assertEqual(result["status"], "not_certified")
                    self.assertNotIn("enclosures", result)
                    continue
                self.assertEqual(result["status"], "certified")
                self.assertEqual(fraction(result["tau"]), tau)
                self.assertEqual(
                    [
                        (fraction(v["lower"]), fraction(v["upper"]))
                        for v in result["enclosures"]
                    ],
                    bounds,
                )
                self.assertEqual(len(result["radii"]), 400)
                self.assertEqual(
                    result["decision"]["status"],
                    "undecidable" if name == "fipy-altered-answer" else "above",
                )
                if name in NAMES[:2]:
                    self.assertGreaterEqual(bounds[19][0], F(99, 100))
                    self.assertLessEqual(bounds[19][1], F(101, 100))
        node = shutil.which("node")
        if not node:
            self.skipTest("Node unavailable; Python independent oracle passed")
        run = subprocess.run(
            [node, str(ROOT / "tests/parity_runner.mjs")],
            input=json.dumps(texts),
            text=True,
            capture_output=True,
            timeout=20,
            check=True,
        )
        observed = json.loads(run.stdout)
        self.assertEqual([row["result"] for row in observed], expected)
        self.assertTrue(all(row["ok"] for row in observed))

    def test_detached_stdlib_sparse_bundle(self):
        text = (ROOT / "examples/fipy-steady400.json").read_text()
        expected = verify_text(text)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            write_bundle(text, base / "proof.zip")
            with zipfile.ZipFile(base / "proof.zip") as archive:
                archive.extractall(base / "proof")
            run = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-S",
                    str(base / "proof/checker.py"),
                    str(base / "proof/certificate.json"),
                ],
                text=True,
                capture_output=True,
                timeout=20,
                check=True,
                cwd=directory,
            )
            self.assertEqual(json.loads(run.stdout), expected)
            self.assertEqual(
                json.loads((base / "proof/verification.json").read_text())["result"],
                expected,
            )


if __name__ == "__main__":
    unittest.main()
