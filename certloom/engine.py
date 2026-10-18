"""Exact verification of square systems containing stored binary64 values.

The dense Neumann-series bound and sparse weighted diagonal-dominance bound
are established numerical verification theory.
This checker certifies the declared equations, not their physical meaning,
source authenticity, or the process that produced a candidate solution.
"""

import json
import math
import re
from fractions import Fraction

MAX_BYTES = 2 * 1024 * 1024
MAX_DIMENSION = 128
MAX_DECIMAL_PLACES = 1000
FORMAT = "certloom-linear-v1"
SPARSE_FORMAT = "certloom-sparse-dd-v1"
MAX_SPARSE_DIMENSION = 4096
MAX_NONZEROS = 32768
_ROOT_KEYS = {"format", "A", "R", "b", "x", "decision"}
_SPARSE_KEYS = {"format", "A", "b", "x", "weights", "decision"}
_INTEGER = re.compile(r"(?:0|-[1-9][0-9]*|[1-9][0-9]*)\Z")
_POSITIVE = re.compile(r"[1-9][0-9]*\Z")


class VerificationError(ValueError):
    """The input is invalid or exceeds the checker's declared resource limits."""


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise VerificationError("Duplicate JSON object key: " + key)
        result[key] = value
    return result


def _constant(_value):
    raise VerificationError("Nonfinite JSON constants are not supported")


def _hex(value, location):
    if not isinstance(value, str) or len(value) > 24:
        raise VerificationError(
            location + " must be a canonical finite binary64 hex string"
        )
    try:
        parsed = float.fromhex(value)
    except (ValueError, OverflowError) as exc:
        raise VerificationError(
            location + " is not a finite binary64 hex value"
        ) from exc
    if not math.isfinite(parsed) or parsed.hex() != value:
        raise VerificationError(
            location + " is not canonical finite Python float.hex()"
        )
    numerator, denominator = parsed.as_integer_ratio()
    return numerator, denominator.bit_length() - 1


def _validate(document):
    if isinstance(document, dict) and document.get("format") == SPARSE_FORMAT:
        return _validate_sparse(document)
    if not isinstance(document, dict) or set(document) != _ROOT_KEYS:
        raise VerificationError(
            "Certificate must contain exactly format, A, R, b, x and decision"
        )
    if document["format"] != FORMAT:
        raise VerificationError("Unsupported certificate format")
    b = document["b"]
    if not isinstance(b, list) or not 1 <= len(b) <= MAX_DIMENSION:
        raise VerificationError("Dimension must be between 1 and 128")
    n = len(b)
    for name in ("A", "R"):
        matrix = document[name]
        if (
            not isinstance(matrix, list)
            or len(matrix) != n
            or any(not isinstance(row, list) or len(row) != n for row in matrix)
        ):
            raise VerificationError(name + " must be a square matrix matching b")
    x = document["x"]
    if not isinstance(x, list) or len(x) != n:
        raise VerificationError("x must match the dimension of b")
    decision = document["decision"]
    if decision is not None:
        if not isinstance(decision, dict) or set(decision) != {"index", "above"}:
            raise VerificationError("Decision must be null or exactly index and above")
        if type(decision["index"]) is not int or not 0 <= decision["index"] < n:
            raise VerificationError("Decision index must be an integer in the system")
        threshold = _hex(decision["above"], "decision.above")
    else:
        threshold = None
    matrices = [
        [
            [_hex(value, name + " coefficient") for value in row]
            for row in document[name]
        ]
        for name in ("A", "R")
    ]
    vectors = [
        [_hex(value, name + " coefficient") for value in document[name]]
        for name in ("b", "x")
    ]
    return n, matrices, vectors, decision, threshold


def _validate_sparse(document):
    if not isinstance(document, dict) or set(document) != _SPARSE_KEYS:
        raise VerificationError(
            "Sparse certificate must contain exactly format, A, b, x, weights and decision"
        )
    A = document["A"]
    if not isinstance(A, dict) or set(A) != {"dimension", "indptr", "indices", "data"}:
        raise VerificationError(
            "Sparse A must contain exactly dimension, indptr, indices and data"
        )
    n = A["dimension"]
    if type(n) is not int or not 1 <= n <= MAX_SPARSE_DIMENSION:
        raise VerificationError(
            "Sparse dimension must be an integer between 1 and 4096"
        )
    indptr, indices, data = A["indptr"], A["indices"], A["data"]
    if not isinstance(indptr, list) or len(indptr) != n + 1:
        raise VerificationError("CSR indptr must have dimension + 1 entries")
    if (
        not isinstance(indices, list)
        or not isinstance(data, list)
        or len(indices) != len(data)
        or len(data) > MAX_NONZEROS
    ):
        raise VerificationError(
            "CSR indices and data must match and have at most 32768 entries"
        )
    nnz = len(data)
    if (
        any(type(v) is not int or not 0 <= v <= nnz for v in indptr)
        or indptr[0] != 0
        or indptr[-1] != nnz
        or any(a > b for a, b in zip(indptr, indptr[1:]))
    ):
        raise VerificationError(
            "CSR indptr must be integer, nondecreasing, start at zero and end at nnz"
        )
    if any(type(j) is not int or not 0 <= j < n for j in indices):
        raise VerificationError(
            "CSR column indices must be integers within the dimension"
        )
    for i in range(n):
        if any(
            indices[k - 1] >= indices[k] for k in range(indptr[i] + 1, indptr[i + 1])
        ):
            raise VerificationError(
                "CSR columns must be strictly increasing in each row; duplicates are refused"
            )
    for name in ("b", "x", "weights"):
        if not isinstance(document[name], list) or len(document[name]) != n:
            raise VerificationError(name + " must match the sparse dimension")
    coefficients = [_hex(value, "A.data coefficient") for value in data]
    if any(pair[0] == 0 for pair in coefficients):
        raise VerificationError("Explicit zero entries are not canonical CSR")
    vectors = [
        [_hex(value, name + " coefficient") for value in document[name]]
        for name in ("b", "x", "weights")
    ]
    if any(pair[0] <= 0 for pair in vectors[2]):
        raise VerificationError("Every sparse weight must be strictly positive")
    decision = document["decision"]
    threshold = None
    if decision is not None:
        if not isinstance(decision, dict) or set(decision) != {"index", "above"}:
            raise VerificationError("Decision must be null or exactly index and above")
        if type(decision["index"]) is not int or not 0 <= decision["index"] < n:
            raise VerificationError("Decision index must be an integer in the system")
        threshold = _hex(decision["above"], "decision.above")
    return n, indptr, indices, coefficients, vectors, decision, threshold


def load_document(text):
    """Decode bounded UTF-8 JSON, refusing duplicates, then validate its schema."""
    if not isinstance(text, str):
        raise VerificationError("Input must be UTF-8 JSON text")
    try:
        if len(text) > MAX_BYTES or len(text.encode("utf-8")) > MAX_BYTES:
            raise VerificationError("Certificate exceeds the 2 MiB input limit")
        document = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except VerificationError:
        raise
    except (ValueError, RecursionError, UnicodeError) as exc:
        raise VerificationError("Invalid UTF-8 JSON certificate") from exc
    _validate(document)
    return document


def _rational(numerator, denominator=1):
    if denominator <= 0:
        raise VerificationError("Internal rational denominator must be positive")
    common = math.gcd(numerator, denominator)
    return {
        "numerator": str(numerator // common),
        "denominator": str(denominator // common),
    }


def verify(document):
    """Recompute the format's exact sufficient bound and decision enclosures."""
    if isinstance(document, dict) and document.get("format") == SPARSE_FORMAT:
        return _verify_sparse(document)
    n, matrices, vectors, decision, threshold = _validate(document)
    # Every stored value is integer / 2**scale. Integer dot products avoid
    # allocating/reducing a Fraction for each multiply and accumulation.
    scale = max(pair[1] for matrix in matrices for row in matrix for pair in row)
    scale = max(scale, *(pair[1] for vector in vectors for pair in vector))
    unit = 1 << scale

    def integer(pair):
        return pair[0] << (scale - pair[1])

    A, R = [[[integer(pair) for pair in row] for row in matrix] for matrix in matrices]
    b, x = [[integer(pair) for pair in vector] for vector in vectors]
    unit2 = unit * unit
    columns = [[(k, A[k][j]) for k in range(n) if A[k][j]] for j in range(n)]
    q_numerator = 0
    for i, row in enumerate(R):
        row_sum = 0
        for j, column in enumerate(columns):
            product = sum(row[k] * value for k, value in column if row[k])
            row_sum += abs((unit2 if i == j else 0) - product)
        q_numerator = max(q_numerator, row_sum)
    residual = [
        b[i] * unit - sum(value * x[j] for j, value in enumerate(row) if value and x[j])
        for i, row in enumerate(A)
    ]
    eta_numerator = max(
        abs(
            sum(
                value * residual[j]
                for j, value in enumerate(row)
                if value and residual[j]
            )
        )
        for row in R
    )
    result = {
        "status": "not_certified",
        "dimension": n,
        "q": _rational(q_numerator, unit2),
        "eta": _rational(eta_numerator, unit2 * unit),
    }
    if q_numerator >= unit2:
        result["reason"] = (
            "The recomputed contraction bound q is at least 1; this method cannot certify the solution."
        )
        return result
    # eta/(1-q) = eta_numerator / (unit*(unit**2-q_numerator)).
    gap = unit2 - q_numerator
    radius_denominator = unit * gap
    result["status"] = "certified"
    result["radius"] = _rational(eta_numerator, radius_denominator)
    result["enclosures"] = [
        {
            "lower": _rational(value * gap - eta_numerator, radius_denominator),
            "upper": _rational(value * gap + eta_numerator, radius_denominator),
        }
        for value in x
    ]
    if decision is not None:
        index = decision["index"]
        lower, upper = x[index] * gap - eta_numerator, x[index] * gap + eta_numerator
        threshold_numerator, threshold_scale = threshold
        threshold_denominator = 1 << threshold_scale
        rhs = threshold_numerator * radius_denominator
        status = (
            "above"
            if lower * threshold_denominator > rhs
            else (
                "not_above" if upper * threshold_denominator <= rhs else "undecidable"
            )
        )
        result["decision"] = {
            "index": index,
            "above": _rational(threshold_numerator, threshold_denominator),
            "status": status,
            "lower": result["enclosures"][index]["lower"].copy(),
            "upper": result["enclosures"][index]["upper"].copy(),
        }
    return result


def _verify_sparse(document):
    n, indptr, indices, coefficients, vectors, decision, threshold = _validate_sparse(
        document
    )
    # One common dyadic denominator makes the two sparse row sums exact.
    # No dense matrix, inverse, or binary64 arithmetic is used in the proof.
    scale = max(pair[1] for vector in vectors for pair in vector)
    scale = max(scale, max((pair[1] for pair in coefficients), default=0))
    unit = 1 << scale

    def integer(pair):
        return pair[0] << (scale - pair[1])

    data = [integer(pair) for pair in coefficients]
    b, x, weights = [[integer(pair) for pair in vector] for vector in vectors]
    gaps, residuals = [], []
    for i in range(n):
        diagonal, off_diagonal, product = 0, 0, 0
        for k in range(indptr[i], indptr[i + 1]):
            j, value = indices[k], data[k]
            product += value * x[j]
            if j == i:
                diagonal = abs(value) * weights[i]
            else:
                off_diagonal += abs(value) * weights[j]
        gaps.append(diagonal - off_diagonal)
        residuals.append(abs(b[i] * unit - product))
    minimum_gap = min(gaps)
    result = {
        "status": "not_certified",
        "dimension": n,
        "method": "weighted-diagonal-dominance",
        "nonzeros": len(data),
        "minimum_gap": _rational(minimum_gap, unit * unit),
    }
    if minimum_gap <= 0:
        result["reason"] = (
            "The recomputed weighted diagonal-dominance gap is not strictly positive in every row; this method cannot certify the solution."
        )
        return result
    # Both residual and gap have denominator unit**2; compare ratios without
    # division. The theorem gives |error_i| <= weight_i * max_i |r_i|/gap_i.
    numerator, denominator = 0, 1
    for residual, gap in zip(residuals, gaps):
        if residual * denominator > numerator * gap:
            numerator, denominator = residual, gap
    result["status"] = "certified"
    result["tau"] = _rational(numerator, denominator)
    radius_denominator = unit * denominator
    radii = [weight * numerator for weight in weights]
    result["radii"] = [_rational(radius, radius_denominator) for radius in radii]
    result["enclosures"] = [
        {
            "lower": _rational(value * denominator - radius, radius_denominator),
            "upper": _rational(value * denominator + radius, radius_denominator),
        }
        for value, radius in zip(x, radii)
    ]
    if decision is not None:
        index = decision["index"]
        lower = x[index] * denominator - radii[index]
        upper = x[index] * denominator + radii[index]
        threshold_numerator, threshold_scale = threshold
        threshold_denominator = 1 << threshold_scale
        rhs = threshold_numerator * radius_denominator
        status = (
            "above"
            if lower * threshold_denominator > rhs
            else "not_above"
            if upper * threshold_denominator <= rhs
            else "undecidable"
        )
        result["decision"] = {
            "index": index,
            "above": _rational(threshold_numerator, threshold_denominator),
            "status": status,
            "lower": result["enclosures"][index]["lower"].copy(),
            "upper": result["enclosures"][index]["upper"].copy(),
        }
    return result


def verify_text(text):
    """Validate and exactly verify a bounded certificate text."""
    return verify(load_document(text))


def _display_rational(value):
    if isinstance(value, Fraction):
        if (
            value.numerator.bit_length() > 16384
            or value.denominator.bit_length() > 16384
        ):
            raise VerificationError("Display rational exceeds the resource limit")
        return value.numerator, value.denominator
    if not isinstance(value, dict) or set(value) != {"numerator", "denominator"}:
        raise VerificationError(
            "Display value must be Fraction or a normalized rational record"
        )
    numerator, denominator = value["numerator"], value["denominator"]
    if (
        not isinstance(numerator, str)
        or not isinstance(denominator, str)
        or len(numerator) > 4096
        or len(denominator) > 4096
        or not _INTEGER.fullmatch(numerator)
        or not _POSITIVE.fullmatch(denominator)
    ):
        raise VerificationError("Invalid display rational")
    numerator, denominator = int(numerator), int(denominator)
    if math.gcd(numerator, denominator) != 1:
        raise VerificationError("Display rational must be normalized")
    return numerator, denominator


def decimal_bound(rational, places=18, direction="lower"):
    """Return an exact outward-rounded decimal string using floor or ceiling."""
    if type(places) is not int or not 0 <= places <= MAX_DECIMAL_PLACES:
        raise VerificationError("Decimal places must be an integer between 0 and 1000")
    if direction not in ("lower", "upper"):
        raise VerificationError("Direction must be lower or upper")
    numerator, denominator = _display_rational(rational)
    scaled = numerator * 10**places
    rounded = (
        scaled // denominator if direction == "lower" else -((-scaled) // denominator)
    )
    sign = "-" if rounded < 0 else ""
    # Bounded display inputs plus 1000 decimal places can exceed CPython's
    # default integer-to-string digit limit. Convert small decimal chunks
    # instead of disabling that process-wide limit.
    magnitude = abs(rounded)
    chunks = []
    while magnitude >= 1_000_000_000:
        magnitude, chunk = divmod(magnitude, 1_000_000_000)
        chunks.append(chunk)
    digits = str(magnitude) + "".join(str(chunk).zfill(9) for chunk in reversed(chunks))
    if places == 0:
        return sign + digits
    digits = digits.zfill(places + 1)
    return sign + digits[:-places] + "." + digits[-places:]
