"""Independent Python/browser engines must agree exactly, not within a tolerance."""

import json
import random
import shutil
import subprocess
import unittest
from pathlib import Path

from certloom.engine import VerificationError, verify_text

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "Node is required for cross-runtime checks")
class ExactParity(unittest.TestCase):
    def test_original_solver_fixtures_and_varied_dyadic_systems_match_exactly(self):
        texts = [
            (ROOT / "examples" / (name + ".json")).read_text()
            for name in (
                "ladder64",
                "hilbert8",
                "hilbert12",
                "wrong-answer",
                "zero-preconditioner",
            )
        ]
        rng = random.Random(19823)
        for _ in range(30):
            n = rng.randrange(1, 7)
            A = [
                [float(rng.randrange(-8, 9) / 8).hex() for _ in range(n)]
                for _ in range(n)
            ]
            R = [
                [float(rng.randrange(-8, 9) / 8).hex() for _ in range(n)]
                for _ in range(n)
            ]
            texts.append(
                json.dumps(
                    {
                        "format": "certloom-linear-v1",
                        "A": A,
                        "R": R,
                        "b": [float(rng.randrange(-8, 9)).hex() for _ in range(n)],
                        "x": [float(rng.randrange(-8, 9) / 4).hex() for _ in range(n)],
                        "decision": {"index": rng.randrange(n), "above": (0.25).hex()},
                    }
                )
            )
        expected = [{"ok": True, "result": verify_text(text)} for text in texts]
        result = subprocess.run(
            ["node", str(ROOT / "tests/parity_runner.mjs")],
            input=json.dumps(texts),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), expected)

    def test_parser_boundaries_and_refusals_match_both_runtimes(self):
        base = {
            "format": "certloom-linear-v1",
            "A": [[(1.0).hex()]],
            "R": [[(1.0).hex()]],
            "b": [(1.0).hex()],
            "x": [(1.0).hex()],
            "decision": {"index": 0, "above": (0.0).hex()},
        }
        text = json.dumps(base)
        variants = [
            "{}",
            "[]",
            text.replace('"index": 0', '"index": 0.0'),
            text.replace('"index": 0', '"index": 0e0'),
            text.replace('"index": 0', '"index": -0'),
            text.replace('"index": 0', '"index": true'),
            text[:-1] + ',"format":"certloom-linear-v1"}',
            text.replace('"above":', '"index":0,"above":'),
            text.replace("0x1.0000000000000p+0", "0x1.00000000000001p+0"),
            text.replace("0x1.0000000000000p+0", "0X1.0000000000000p+0"),
            text.replace("0x1.0000000000000p+0", "nan"),
            " " * (2 * 1024 * 1024 + 1),
            text,
        ]
        expected = []
        for item in variants:
            try:
                expected.append({"ok": True, "result": verify_text(item)})
            except VerificationError:
                expected.append({"ok": False})
        result = subprocess.run(
            ["node", str(ROOT / "tests/parity_runner.mjs")],
            input=json.dumps(variants),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), expected)


if __name__ == "__main__":
    unittest.main()
