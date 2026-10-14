"""Encode a producer's proposed system explicitly as stored binary64 values."""

import json
import math

from .engine import MAX_DIMENSION, VerificationError, load_document


def make_certificate(A, b, x, R, decision=None):
    """Solver independent. Conversion to binary64 is explicit, not exact decimal input."""
    try:
        n = len(b)
        if not 1 <= n <= MAX_DIMENSION or len(x) != n or len(A) != n or len(R) != n:
            raise VerificationError("Unsupported or inconsistent system dimension.")
        if any(len(row) != n for matrix in (A, R) for row in matrix):
            raise VerificationError("Matrices must be square with the same dimension.")
    except TypeError as error:
        raise VerificationError(
            "Supply finite arrays with known dimensions."
        ) from error

    def encode(value):
        if isinstance(value, bool):
            raise VerificationError("Boolean coefficients are unsupported.")
        try:
            value = float(value)
        except (TypeError, ValueError, OverflowError) as error:
            raise VerificationError(
                "Coefficients must convert to finite binary64."
            ) from error
        if not math.isfinite(value):
            raise VerificationError("Coefficients must convert to finite binary64.")
        return value.hex()

    document = {
        "format": "certloom-linear-v1",
        "A": [[encode(v) for v in row] for row in A],
        "R": [[encode(v) for v in row] for row in R],
        "b": [encode(v) for v in b],
        "x": [encode(v) for v in x],
        "decision": None,
    }
    if decision is not None:
        if not isinstance(decision, dict) or set(decision) != {"index", "above"}:
            raise VerificationError("Decision requires index and above.")
        document["decision"] = {
            "index": decision["index"],
            "above": encode(decision["above"]),
        }
    return load_document(json.dumps(document))
