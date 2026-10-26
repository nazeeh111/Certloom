"""Encode a producer's proposed system explicitly as stored binary64 values."""

import json
import math
import numbers
import operator

from .engine import (
    MAX_DIMENSION,
    MAX_SPARSE_DIMENSION,
    MAX_NONZEROS,
    VerificationError,
    load_document,
)


def _encode(value):
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

    document = {
        "format": "certloom-linear-v1",
        "A": [[_encode(v) for v in row] for row in A],
        "R": [[_encode(v) for v in row] for row in R],
        "b": [_encode(v) for v in b],
        "x": [_encode(v) for v in x],
        "decision": None,
    }
    if decision is not None:
        if not isinstance(decision, dict) or set(decision) != {"index", "above"}:
            raise VerificationError("Decision requires index and above.")
        document["decision"] = {
            "index": decision["index"],
            "above": _encode(decision["above"]),
        }
    return load_document(json.dumps(document))


def make_sparse_certificate(indptr, indices, data, b, x, weights, decision=None):
    """Encode canonical CSR and positive weights as explicit stored binary64.

    Dimension is inferred from b. No sorting, duplicate aggregation, zero
    removal, matrix expansion or choice of weights is performed here.
    """
    try:
        n = len(b)
        if (
            not 1 <= n <= MAX_SPARSE_DIMENSION
            or len(x) != n
            or len(weights) != n
            or len(indptr) != n + 1
            or len(indices) != len(data)
            or len(data) > MAX_NONZEROS
        ):
            raise VerificationError("Unsupported or inconsistent sparse dimensions.")
    except TypeError as error:
        raise VerificationError(
            "Supply finite arrays with known dimensions."
        ) from error

    def index(value):
        # Integral includes NumPy integer scalars without importing NumPy,
        # while excluding floats, bool and NumPy's distinct boolean type.
        if isinstance(value, bool) or not isinstance(value, numbers.Integral):
            raise VerificationError(
                "CSR indices must be integers, not booleans or floats."
            )
        return operator.index(value)

    document = {
        "format": "certloom-sparse-dd-v1",
        "A": {
            "dimension": n,
            "indptr": [index(v) for v in indptr],
            "indices": [index(v) for v in indices],
            "data": [_encode(v) for v in data],
        },
        "b": [_encode(v) for v in b],
        "x": [_encode(v) for v in x],
        "weights": [_encode(v) for v in weights],
        "decision": None,
    }
    if decision is not None:
        if not isinstance(decision, dict) or set(decision) != {"index", "above"}:
            raise VerificationError("Decision requires index and above.")
        document["decision"] = {
            "index": index(decision["index"]),
            "above": _encode(decision["above"]),
        }
    return load_document(json.dumps(document))
