"""Sparse certificates checked against independent rational arithmetic."""

import copy
import json
import math
import random
import unittest
from fractions import Fraction

from certloom.engine import VerificationError, load_document, verify, verify_text
from certloom import producer


def certificate(A, b, x, weights, decision=None):
    n = len(b)
    indptr, indices, data = [0], [], []
    for row in A:
        for j, value in enumerate(row):
            if value:
                indices.append(j)
                data.append(float(value).hex())
        indptr.append(len(data))
    return {
        "format": "certloom-sparse-dd-v1",
        "A": {"dimension": n, "indptr": indptr, "indices": indices, "data": data},
        "b": [float(v).hex() for v in b],
        "x": [float(v).hex() for v in x],
        "weights": [float(v).hex() for v in weights],
        "decision": decision,
    }


def rational(record):
    value = Fraction(int(record["numerator"]), int(record["denominator"]))
    assert record == {
        "numerator": str(value.numerator),
        "denominator": str(value.denominator),
    }
    return value


def solve(A, b):
    """Small independent rational elimination, used only by tests."""
    rows = [
        [Fraction(float(v)) for v in row] + [Fraction(float(rhs))]
        for row, rhs in zip(A, b)
    ]
    n = len(rows)
    for k in range(n):
        pivot = next(i for i in range(k, n) if rows[i][k])
        rows[k], rows[pivot] = rows[pivot], rows[k]
        divisor = rows[k][k]
        rows[k] = [value / divisor for value in rows[k]]
        for i in range(n):
            if i != k:
                factor = rows[i][k]
                rows[i] = [a - factor * b for a, b in zip(rows[i], rows[k])]
    return [row[-1] for row in rows]


class SparseTests(unittest.TestCase):
    def check_reference(self, A, b, x, weights):
        result = verify(certificate(A, b, x, weights))
        A = [[Fraction(float(v)) for v in row] for row in A]
        b, x, weights = [
            [Fraction(float(v)) for v in vector] for vector in (b, x, weights)
        ]
        gaps = [
            abs(row[i]) * weights[i]
            - sum(abs(a) * weights[j] for j, a in enumerate(row) if j != i)
            for i, row in enumerate(A)
        ]
        self.assertEqual(rational(result["minimum_gap"]), min(gaps))
        self.assertEqual(result["method"], "weighted-diagonal-dominance")
        self.assertEqual(result["nonzeros"], sum(bool(v) for row in A for v in row))
        self.assertFalse({"q", "eta", "radius"} & result.keys())
        if min(gaps) <= 0:
            self.assertEqual(result["status"], "not_certified")
            self.assertFalse({"tau", "radii", "enclosures", "decision"} & result.keys())
            return result
        tau = max(
            abs(rhs - sum(a * v for a, v in zip(row, x))) / gap
            for row, rhs, gap in zip(A, b, gaps)
        )
        self.assertEqual(result["status"], "certified")
        self.assertEqual(rational(result["tau"]), tau)
        solution = solve(A, b)
        for i, enclosure in enumerate(result["enclosures"]):
            self.assertEqual(rational(result["radii"][i]), weights[i] * tau)
            lo, hi = rational(enclosure["lower"]), rational(enclosure["upper"])
            self.assertEqual(
                (lo, hi), (x[i] - weights[i] * tau, x[i] + weights[i] * tau)
            )
            self.assertLessEqual(lo, solution[i])
            self.assertLessEqual(solution[i], hi)
        return result

    def test_weighted_mixed_sign_nonsymmetric(self):
        self.check_reference([[2, -1], [4, -3]], [1, 2], [0.25, -0.5], [1, 1.5])

    def test_small_rational_systems(self):
        rng = random.Random(85291)
        for n in range(1, 7):
            for _ in range(5):
                weights = [rng.choice([0.5, 1, 2]) for _ in range(n)]
                A = [
                    [rng.choice([0, 0, -0.5, 0.25]) if i != j else 0 for j in range(n)]
                    for i in range(n)
                ]
                for i in range(n):
                    A[i][i] = rng.choice([-1, 1]) * (
                        1
                        + sum(abs(a) * weights[j] for j, a in enumerate(A[i]))
                        / weights[i]
                    )
                self.check_reference(
                    A,
                    [rng.randrange(-5, 6) / 2 for _ in range(n)],
                    [rng.randrange(-5, 6) / 4 for _ in range(n)],
                    weights,
                )

    def test_failed_premise_is_not_singularity(self):
        self.check_reference([[1, 1], [-1, 1]], [2, 3], [0, 0], [1, 1])
        for A in ([[0, 0], [0, 1]], [[0, 1], [1, 2]]):
            self.check_reference(A, [1, 1], [0, 0], [1, 1])

    def test_subnormal_and_extreme_exponents(self):
        tiny = math.ulp(0.0)
        self.check_reference([[tiny]], [tiny], [0], [tiny])
        huge = float.fromhex("0x1.fffffffffffffp+1023")
        self.check_reference([[huge]], [huge], [0], [huge])
        self.check_reference(
            [[huge, 0], [0, tiny]], [huge, tiny], [huge, tiny], [tiny, huge]
        )

    def test_weight_scaling_and_exact_residual(self):
        A, b, x = [[3, -1], [-1, 3]], [2, 2], [1, 1]
        exact = self.check_reference(A, b, x, [1, 1])
        self.assertEqual(rational(exact["tau"]), 0)
        a = verify(certificate(A, b, [0, 0], [1, 2]))
        c = verify(certificate(A, b, [0, 0], [8, 16]))
        self.assertEqual(a["radii"], c["radii"])

    def test_strict_decision_boundaries(self):
        for above, expected in (
            (-2, "above"),
            (-1, "undecidable"),
            (0, "undecidable"),
            (1, "not_above"),
        ):
            doc = certificate(
                [[1]], [1], [0], [1], {"index": 0, "above": float(above).hex()}
            )
            result = verify(doc)
            self.assertEqual(result["decision"]["status"], expected)
            self.assertEqual(
                result["decision"]["lower"], result["enclosures"][0]["lower"]
            )

    def test_producer_roundtrip_and_no_reordering(self):
        document = producer.make_sparse_certificate(
            [0, 2, 4],
            [0, 1, 0, 1],
            [2, -1, 4, -3],
            [1, 2],
            [0.25, -0.5],
            [1, 1.5],
            {"index": 1, "above": 0},
        )
        self.assertEqual(verify(document), verify_text(json.dumps(document)))
        with self.assertRaises(VerificationError):
            producer.make_sparse_certificate([0, 2], [0, 0], [1, 2], [1], [0], [1])
        for bad in (True, 0.0):
            with self.assertRaises(VerificationError):
                producer.make_sparse_certificate([0, 1], [bad], [1], [1], [0], [1])

    def test_schema_refusals(self):
        base = certificate([[2, -1], [0, 2]], [1, 1], [0, 0], [1, 1])
        mutations = [
            lambda d: d.update(extra=1),
            lambda d: d["A"].update(extra=1),
            lambda d: d["A"].update(dimension=True),
            lambda d: d["A"].update(dimension=2.0),
            lambda d: d["A"].update(dimension=0),
            lambda d: d["A"].update(dimension=4097),
            lambda d: d["A"].update(indptr=[0, 3, 2]),
            lambda d: d["A"].update(indptr=[1, 2, 3]),
            lambda d: d["A"].update(indptr=[0, 2]),
            lambda d: d["A"].update(indptr=[0, True, 3]),
            lambda d: d["A"].update(indptr=[0, 2.0, 3]),
            lambda d: d["A"].update(indices=[0, 0, 1]),
            lambda d: d["A"].update(indices=[1, 0, 1]),
            lambda d: d["A"].update(indices=[0, -1, 1]),
            lambda d: d["A"].update(indices=[0, 2, 1]),
            lambda d: d["A"].update(indices=[0, True, 1]),
            lambda d: d["A"].update(indices=[0, 1.0, 1]),
            lambda d: d["A"].update(data=[]),
            lambda d: d["A"]["data"].__setitem__(0, "0x0.0p+0"),
            lambda d: d["A"]["data"].__setitem__(0, "-0x0.0p+0"),
            lambda d: d["A"]["data"].__setitem__(0, "nan"),
            lambda d: d["A"]["data"].__setitem__(0, "0x1p+1"),
            lambda d: d["A"]["data"].__setitem__(0, 2),
            lambda d: d["weights"].__setitem__(0, "0x0.0p+0"),
            lambda d: d["weights"].__setitem__(0, "-0x1.0000000000000p+0"),
            lambda d: d.update(x=[]),
            lambda d: d.update(b=[]),
            lambda d: d.update(weights=[]),
            lambda d: d["x"].__setitem__(0, "inf"),
            lambda d: d["b"].__setitem__(0, "nan"),
            lambda d: d["weights"].__setitem__(0, "inf"),
            lambda d: d.update(decision={"index": True, "above": "0x0.0p+0"}),
            lambda d: d.update(decision={"index": 2, "above": "0x0.0p+0"}),
            lambda d: d.update(decision={"index": 0, "above": "0x0.0p+0", "extra": 1}),
        ]
        for mutation in mutations:
            doc = copy.deepcopy(base)
            mutation(doc)
            with self.subTest(doc=doc), self.assertRaises(VerificationError):
                verify(doc)

    def test_json_refusals(self):
        text = json.dumps(certificate([[1]], [1], [0], [1]))
        for invalid in (
            text.replace('"dimension": 1', '"dimension": 1, "dimension": 1'),
            text.replace('"decision": null', '"decision": NaN'),
            text + " " * (2 * 1024 * 1024),
        ):
            with self.assertRaises(VerificationError):
                load_document(invalid)

    def test_maximum_dimension_is_sparse(self):
        n = 4096
        doc = {
            "format": "certloom-sparse-dd-v1",
            "A": {
                "dimension": n,
                "indptr": list(range(n + 1)),
                "indices": list(range(n)),
                "data": [float(1).hex()] * n,
            },
            "b": [float(1).hex()] * n,
            "x": [float(1).hex()] * n,
            "weights": [float(1).hex()] * n,
            "decision": None,
        }
        self.assertEqual(verify_text(json.dumps(doc))["status"], "certified")
        doc["A"]["data"] = [float(1).hex()] * 32769
        doc["A"]["indices"] = [0] * 32769
        with self.assertRaises(VerificationError):
            verify(doc)

    def test_maximum_nonzeros_and_producer_refusals(self):
        n = 4096
        indices, data, indptr = [], [], [0]
        for i in range(n):
            columns = sorted((i + j) % n for j in range(8))
            indices.extend(columns)
            data.extend(9 if j == i else -1 for j in columns)
            indptr.append(len(data))
        document = producer.make_sparse_certificate(
            indptr, indices, data, [2] * n, [1] * n, [1] * n
        )
        result = verify(document)
        self.assertEqual(result["nonzeros"], 32768)
        self.assertEqual(rational(result["minimum_gap"]), 2)
        self.assertEqual(rational(result["tau"]), 0)
        for bad_data, weights in (
            ([0], [1]),
            ([float("nan")], [1]),
            ([1], [0]),
            ([1], [-1]),
        ):
            with self.assertRaises(VerificationError):
                producer.make_sparse_certificate(
                    [0, 1], [0], bad_data, [1], [0], weights
                )
        with self.assertRaises(VerificationError):
            producer.make_sparse_certificate(
                [0, 32769], [0] * 32769, [1] * 32769, [1], [0], [1]
            )


if __name__ == "__main__":
    unittest.main()
