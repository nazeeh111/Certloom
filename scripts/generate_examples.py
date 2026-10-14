"""Original NumPy-produced equations and exact independent validation oracles.

This producer is optional. The shipped verifiers do not import NumPy.
"""

import json
import sys
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from certloom.engine import verify  # noqa: E402
from certloom.producer import make_certificate  # noqa: E402


def oracle(A, b):
    """Separate exact Gauss-Jordan solution, not the certification algorithm."""
    rows = [
        [F.from_float(float(v)) for v in row] + [F.from_float(float(rhs))]
        for row, rhs in zip(A, b)
    ]
    n = len(rows)
    for j in range(n):
        pivot = next(i for i in range(j, n) if rows[i][j])
        rows[j], rows[pivot] = rows[pivot], rows[j]
        d = rows[j][j]
        rows[j] = [v / d for v in rows[j]]
        for i in range(n):
            if i != j:
                d = rows[i][j]
                rows[i] = [u - d * v for u, v in zip(rows[i], rows[j])]
    return [row[-1] for row in rows]


def exact(record):
    return F(int(record["numerator"]), int(record["denominator"]))


def generate(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    entries, proofs = [], []

    def emit(
        identifier,
        title,
        description,
        A,
        b,
        x,
        R,
        index,
        threshold,
        expected,
        truth=None,
    ):
        document = make_certificate(A, b, x, R, {"index": index, "above": threshold})
        data = (json.dumps(document, separators=(",", ":")) + "\n").encode()
        result = verify(document)
        assert result["status"] == expected
        if truth is None:
            truth = oracle(A, b)
        actual = max(abs(F.from_float(float(v)) - t) for v, t in zip(x, truth))
        if expected == "certified":
            assert actual <= exact(result["radius"])
            for t, enclosure in zip(truth, result["enclosures"]):
                assert exact(enclosure["lower"]) <= t <= exact(enclosure["upper"])
        name = identifier + ".json"
        (destination / name).write_bytes(data)
        entries.append(
            {
                "id": identifier,
                "title": title,
                "description": description,
                "file": name,
                "bytes": len(data),
                "sha256": sha256(data).hexdigest(),
            }
        )
        proofs.append(
            {
                "id": identifier,
                "status": result["status"],
                "floatResidualInf": float(np.linalg.norm(A @ x - b, np.inf)),
                "actualForwardError": str(actual),
                "result": result,
            }
        )
        return result

    n, k = 64, 32
    A = 2 * np.eye(n) - np.eye(n, k=1) - np.eye(n, k=-1)
    b = np.zeros(n)
    b[k - 1] = 1.0
    x, R = np.linalg.solve(A, b), np.linalg.inv(A)
    truth = [F(min(i, k) * (n + 1 - max(i, k)), n + 1) for i in range(1, n + 1)]
    result = emit(
        "ladder64",
        "A voltage decision with evidence",
        "An original ideal 64-node resistor ladder. Certify whether node 32 is above 16 V; this models equations, not measured hardware.",
        A,
        b,
        x,
        R,
        k - 1,
        16.0,
        "certified",
        truth,
    )
    assert result["decision"]["status"] == "above"
    for size in (8, 12):
        A = np.array([[1.0 / (i + j + 1) for j in range(size)] for i in range(size)])
        b = A @ np.ones(size)
        x, R = np.linalg.solve(A, b), np.linalg.inv(A)
        emit(
            "hilbert" + str(size),
            "Small residual, " + ("bounded error" if size == 8 else "failed proof"),
            "Original ill-conditioned stored binary64 equations. A small floating residual alone does not establish answer accuracy.",
            A,
            b,
            x,
            R,
            0,
            1.0,
            "certified" if size == 8 else "not_certified",
        )
    epsilon = 2.0**-40
    A = np.array([[1.0, 1.0], [1.0, 1.0 + epsilon]])
    b = np.array([2.0, 2.0 + epsilon])
    R = np.linalg.inv(A)
    wrong = emit(
        "wrong-answer",
        "An unsupported decision",
        "A deliberately altered answer has a tiny residual. Its wide valid enclosure cannot establish the threshold claim.",
        A,
        b,
        np.array([0.0, 2.0]),
        R,
        0,
        0.5,
        "certified",
    )
    assert wrong["decision"]["status"] == "undecidable"
    emit(
        "zero-preconditioner",
        "A refused certificate",
        "Even a correct answer cannot pass this proof with an unusable zero approximate inverse. Refusal is useful information.",
        A,
        b,
        np.array([1.0, 1.0]),
        np.zeros((2, 2)),
        0,
        0.5,
        "not_certified",
    )
    manifest = {
        "version": 1,
        "producer": {
            "numpy": np.__version__,
            "script": "scripts/generate_examples.py",
            "candidate": "numpy.linalg.solve; wrong-answer explicitly altered; zero-preconditioner explicitly altered",
            "scope": "Original mathematical equations, not hardware or measured data",
            "oracle": "Exact analytic ladder Green function; independent rational Gauss-Jordan for smaller systems",
        },
        "examples": entries,
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (destination / "validation.json").write_text(
        json.dumps({"numpy": np.__version__, "cases": proofs}, indent=2) + "\n"
    )
    return manifest


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    manifest = generate(args.out)
    print(
        json.dumps(
            {
                "out": args.out,
                "examples": len(manifest["examples"]),
                "numpy": np.__version__,
            }
        )
    )
