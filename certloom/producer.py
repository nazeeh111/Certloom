"""Encode a producer's proposed system explicitly as stored binary64 values."""

import json
import math
import numbers
import operator

from .engine import (
    MAX_DIMENSION,
    MAX_SPARSE_DIMENSION,
    MAX_NONZEROS,
    SPARSE_FORMAT,
    VerificationError,
    load_document,
    verify,
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


def make_sparse_certificate(indptr, indices, data, b, x, weights=None, decision=None):
    """Encode canonical CSR and positive weights as explicit stored binary64.

    Dimension is inferred from b. No sorting, duplicate aggregation, zero
    removal or matrix expansion is performed. Omit weights to search for
    a witness. Explicit weights are preserved, even when the proof fails.
    """
    try:
        n = len(b)
        if (
            not 1 <= n <= MAX_SPARSE_DIMENSION
            or len(x) != n
            or (weights is not None and len(weights) != n)
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
        "weights": [_encode(v) for v in weights] if weights is not None else [1.0.hex()] * n,
        "decision": None,
    }
    if decision is not None:
        if not isinstance(decision, dict) or set(decision) != {"index", "above"}:
            raise VerificationError("Decision requires index and above.")
        document["decision"] = {
            "index": index(decision["index"]),
            "above": _encode(decision["above"]),
        }
    document = load_document(json.dumps(document))
    if weights is None:
        return reweight_sparse_certificate(document)
    return document


def reweight_sparse_certificate(document):
    """Find a sufficient positive scaling for a validated sparse system.

    Search is bounded. Failure to find weights makes no singularity claim.
    Only weights change, and the exact checker admits every returned witness.
    """
    if not isinstance(document, dict) or document.get("format") != SPARSE_FORMAT:
        raise VerificationError("Weight search requires a sparse CSR certificate.")
    candidate = dict(document)
    if verify(candidate)["status"] == "certified":
        return candidate

    matrix = candidate["A"]
    n = matrix["dimension"]
    weights = [1.0] * n
    unit = [1.0.hex()] * n
    if candidate["weights"] != unit:
        candidate["weights"] = unit
        if verify(candidate)["status"] == "certified":
            return candidate

    rows = []
    for i, (start, end) in enumerate(zip(matrix["indptr"], matrix["indptr"][1:])):
        entries = [(matrix["indices"][k], abs(float.fromhex(matrix["data"][k])))
                   for k in range(start, end)]
        diagonal = next((value for col, value in entries if col == i), 0.0)
        if diagonal == 0.0:
            raise VerificationError("A missing diagonal precludes strict weighted dominance.")
        rows.append([(col, value / diagonal) for col, value in entries if col != i])

    # Gauss-Seidel sweeps on (I - |D|^-1 |A-D|)w = 1 propose a positive gap.
    # The floating-point solve is only a producer; certification remains exact.
    for sweep in range(1, 257):
        for i, row in enumerate(rows):
            value = 1.0 + sum(factor * weights[j] for j, factor in row)
            if not math.isfinite(value):
                raise VerificationError("Weight search exceeded the finite binary64 range.")
            weights[i] = value
        if (sweep & (sweep - 1)) == 0:
            candidate["weights"] = [value.hex() for value in weights]
            if verify(candidate)["status"] == "certified":
                return load_document(json.dumps(candidate, separators=(",", ":")))
    raise VerificationError("No certified weights found within 256 sweeps.")
