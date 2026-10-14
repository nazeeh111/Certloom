import copy
import json
import random
import unittest
from fractions import Fraction

from certloom.engine import (
    VerificationError,
    decimal_bound,
    load_document,
    verify,
    verify_text,
)


def certificate(A, b, x, R, decision=None):
    return {
        "format": "certloom-linear-v1",
        "A": [[float(v).hex() for v in row] for row in A],
        "R": [[float(v).hex() for v in row] for row in R],
        "b": [float(v).hex() for v in b],
        "x": [float(v).hex() for v in x],
        "decision": None
        if decision is None
        else {"index": decision[0], "above": float(decision[1]).hex()},
    }


def rational(record):
    value = Fraction(int(record["numerator"]), int(record["denominator"]))
    assert str(value.numerator) == record["numerator"]
    assert str(value.denominator) == record["denominator"]
    return value


def reference(document):
    def parse(text):
        return Fraction.from_float(float.fromhex(text))

    A, R = [[[parse(v) for v in row] for row in document[key]] for key in ("A", "R")]
    b, x = [[parse(v) for v in document[key]] for key in ("b", "x")]
    n = len(x)
    residual = [b[i] - sum(A[i][j] * x[j] for j in range(n)) for i in range(n)]
    q = max(
        sum(
            abs(Fraction(int(i == j)) - sum(R[i][k] * A[k][j] for k in range(n)))
            for j in range(n)
        )
        for i in range(n)
    )
    eta = max(abs(sum(R[i][j] * residual[j] for j in range(n))) for i in range(n))
    return q, eta, eta / (1 - q) if q < 1 else None


class EngineTests(unittest.TestCase):
    def test_certified_random_systems_match_independent_fraction_reference(self):
        rng = random.Random(811)
        for _ in range(30):
            n = 4
            A = [
                [int(i == j) + rng.randint(-2, 2) / 32 for j in range(n)]
                for i in range(n)
            ]
            R = [[int(i == j) for j in range(n)] for i in range(n)]
            b = [rng.randint(-10, 10) / 8 for _ in range(n)]
            x = [rng.randint(-10, 10) / 8 for _ in range(n)]
            document = certificate(A, b, x, R)
            q, eta, radius = reference(document)
            self.assertLess(q, 1)
            result = verify(document)
            self.assertEqual(result["status"], "certified")
            self.assertEqual(rational(result["q"]), q)
            self.assertEqual(rational(result["eta"]), eta)
            self.assertEqual(rational(result["radius"]), radius)
            for candidate, enclosure in zip(x, result["enclosures"]):
                self.assertEqual(
                    rational(enclosure["lower"]), Fraction(candidate) - radius
                )
                self.assertEqual(
                    rational(enclosure["upper"]), Fraction(candidate) + radius
                )

    def test_exact_solution_zero_radius_and_every_component(self):
        document = certificate([[2, 0], [0, 4]], [6, 20], [3, 5], [[0.5, 0], [0, 0.25]])
        result = verify(document)
        self.assertEqual(result["status"], "certified")
        self.assertEqual(rational(result["radius"]), 0)
        self.assertEqual(len(result["enclosures"]), 2)
        for enclosure, expected in zip(result["enclosures"], (3, 5)):
            self.assertEqual(rational(enclosure["lower"]), expected)
            self.assertEqual(rational(enclosure["upper"]), expected)
        self.assertNotIn("decision", result)

    def test_independent_fraction_reference_across_signed_dyadic_systems(self):
        rng = random.Random(519)
        for _ in range(30):
            A = [[rng.randint(-16, 16) / 8 for _ in range(3)] for _ in range(3)]
            R = [[rng.randint(-16, 16) / 16 for _ in range(3)] for _ in range(3)]
            b = [rng.randint(-20, 20) / 8 for _ in range(3)]
            x = [rng.randint(-20, 20) / 8 for _ in range(3)]
            document = certificate(A, b, x, R)
            q, eta, radius = reference(document)
            result = verify(document)
            self.assertEqual(rational(result["q"]), q)
            self.assertEqual(rational(result["eta"]), eta)
            self.assertEqual(
                result["status"], "certified" if q < 1 else "not_certified"
            )
            if radius is not None:
                self.assertEqual(rational(result["radius"]), radius)
                for candidate, enclosure in zip(x, result["enclosures"]):
                    self.assertEqual(
                        rational(enclosure["lower"]), Fraction(candidate) - radius
                    )
                    self.assertEqual(
                        rational(enclosure["upper"]), Fraction(candidate) + radius
                    )

    def test_nonzero_contraction_fraction_reference(self):
        document = certificate(
            [[2, 1], [1, 3]], [1, 2], [0.199, 0.601], [[0.599, -0.201], [-0.201, 0.401]]
        )
        result = verify(document)
        q, eta, radius = reference(document)
        self.assertLess(q, 1)
        self.assertEqual(rational(result["q"]), q)
        self.assertEqual(rational(result["eta"]), eta)
        self.assertEqual(rational(result["radius"]), radius)
        for actual, enclosure in zip(
            (Fraction(1, 5), Fraction(3, 5)), result["enclosures"]
        ):
            self.assertLessEqual(rational(enclosure["lower"]), actual)
            self.assertLessEqual(actual, rational(enclosure["upper"]))

    def test_analytic_64_node_ladder_all_enclosures(self):
        n, k = 64, 32
        A = [
            [2 if i == j else -1 if abs(i - j) == 1 else 0 for j in range(n)]
            for i in range(n)
        ]
        oracle = [
            Fraction(min(i, k) * (n + 1 - max(i, k)), n + 1) for i in range(1, n + 1)
        ]
        R = [
            [
                float(Fraction(min(i, j) * (n + 1 - max(i, j)), n + 1))
                for j in range(1, n + 1)
            ]
            for i in range(1, n + 1)
        ]
        b = [int(i == k) for i in range(1, n + 1)]
        document = certificate(A, b, list(map(float, oracle)), R, (k - 1, 16))
        result = verify(document)
        self.assertEqual(result["status"], "certified")
        self.assertEqual(result["decision"]["status"], "above")
        for actual, enclosure in zip(oracle, result["enclosures"]):
            self.assertLessEqual(rational(enclosure["lower"]), actual)
            self.assertLessEqual(actual, rational(enclosure["upper"]))

    def test_small_residual_does_not_mean_accurate_answer(self):
        e = 2.0**-40
        document = certificate(
            [[1, 1], [1, 1 + e]],
            [2, 2 + e],
            [0, 2],
            [[1 + 2**40, -(2**40)], [-(2**40), 2**40]],
            (0, 0.5),
        )
        result = verify(document)
        self.assertEqual(result["status"], "certified")
        self.assertEqual(rational(result["radius"]), 1)
        self.assertEqual(result["decision"]["status"], "undecidable")

    def test_decision_strict_above_and_inclusive_not_above_boundaries(self):
        # Exact solution=2, candidate=3, enclosure=[2,4].
        document = certificate([[1]], [2], [3], [[1]])
        for threshold, expected in (
            (1, "above"),
            (2, "undecidable"),
            (3, "undecidable"),
            (4, "not_above"),
            (5, "not_above"),
        ):
            document["decision"] = {"index": 0, "above": float(threshold).hex()}
            result = verify(document)["decision"]
            self.assertEqual(result["status"], expected)
            self.assertEqual(rational(result["lower"]), 2)
            self.assertEqual(rational(result["upper"]), 4)
        document = certificate([[1]], [2], [2], [[1]], (0, 2))
        self.assertEqual(verify(document)["decision"]["status"], "not_above")

    def test_singular_or_unusable_preconditioner_cannot_certify(self):
        for document in (
            certificate([[0]], [0], [0], [[1]], (0, -1)),
            certificate([[1]], [2], [2], [[0]], (0, 1)),
            certificate([[1]], [2], [2], [[2]], (0, 1)),
        ):
            result = verify(document)
            self.assertEqual(result["status"], "not_certified")
            self.assertGreaterEqual(rational(result["q"]), 1)
            for field in ("radius", "enclosures", "decision"):
                self.assertNotIn(field, result)
            self.assertTrue(result["reason"])

    def test_subnormal_and_maximum_binary64_use_exact_arithmetic(self):
        smallest = float.fromhex("0x0.0000000000001p-1022")
        biggest = float.fromhex("0x1.fffffffffffffp+1023")
        document = certificate(
            [[1, 0], [0, 1]], [smallest, biggest], [0, biggest], [[1, 0], [0, 1]]
        )
        result = verify(document)
        self.assertEqual(rational(result["radius"]), Fraction.from_float(smallest))
        for actual, enclosure in zip((smallest, biggest), result["enclosures"]):
            self.assertLessEqual(
                rational(enclosure["lower"]), Fraction.from_float(actual)
            )
            self.assertLessEqual(
                Fraction.from_float(actual), rational(enclosure["upper"])
            )

    def test_negative_zero_is_canonical_but_has_exact_zero_value(self):
        document = certificate([[1]], [0], [-0.0], [[1]], (0, -0.0))
        result = verify(document)
        self.assertEqual(rational(result["radius"]), 0)
        self.assertEqual(result["decision"]["status"], "not_above")

    def test_text_roundtrip_and_duplicate_key_refusal(self):
        document = certificate([[1]], [2], [2], [[1]])
        text = json.dumps(document)
        self.assertEqual(load_document(text), document)
        self.assertEqual(verify_text(text), verify(document))
        for duplicate in (
            text.replace('"format":', '"format":"bad","format":', 1),
            text.replace(
                '"decision": null',
                '"decision":{"index":0,"index":0,"above":"0x0.0p+0"}',
            ),
        ):
            with self.assertRaises(VerificationError):
                load_document(duplicate)

    def test_extra_keys_format_and_wrong_dimensions_refused(self):
        base = certificate([[1]], [2], [2], [[1]])
        variants = []
        for key, value in (
            ("radius", 0),
            ("format", "unknown"),
            ("A", []),
            ("R", [[1]]),
            ("x", []),
            ("b", ["0x0.0p+0"] * 129),
        ):
            document = copy.deepcopy(base)
            document[key] = value
            variants.append(document)
        document = copy.deepcopy(base)
        del document["decision"]
        variants.append(document)
        for document in variants:
            with self.assertRaises(VerificationError):
                verify(document)

    def test_noncanonical_nonfinite_and_rounded_hex_refused(self):
        base = certificate([[1]], [2], [2], [[1]])
        invalid = (
            "nan",
            "inf",
            "-inf",
            "0X1.0000000000000p+0",
            "+0x1.0000000000000p+0",
            "0x1p+0",
            "0x1.00000000000000p+0",
            "0x1.0000000000001p-1074",
            "0x0.0000000000000p-1022",
            "0x1.0000000000000p+1024",
            " 0x1.0000000000000p+0",
            1,
            True,
            None,
            "x" * 100,
        )
        for value in invalid:
            document = copy.deepcopy(base)
            document["A"][0][0] = value
            with self.assertRaises(VerificationError):
                verify(document)

    def test_decision_schema_and_boolean_index_refused(self):
        base = certificate([[1]], [2], [2], [[1]])
        for decision in (
            [],
            {},
            True,
            {"index": True, "above": "0x0.0p+0"},
            {"index": 1, "above": "0x0.0p+0"},
            {"index": -1, "above": "0x0.0p+0"},
            {"index": 0.0, "above": "0x0.0p+0"},
            {"index": 0, "above": "0x0.0p+0", "status": "above"},
        ):
            document = copy.deepcopy(base)
            document["decision"] = decision
            with self.assertRaises(VerificationError):
                verify(document)

    def test_utf8_json_bounds_and_invalid_json(self):
        for text in (
            " " * (2 * 1024 * 1024 + 1),
            "é" * (1024 * 1024 + 1),
            "\ud800",
            "[]",
            "{",
            '{"x":NaN}',
            "[" * 1200 + "]" * 1200,
            123,
        ):
            with self.assertRaises(VerificationError):
                load_document(text)

    def test_decimal_bounds_are_outward_for_both_signs(self):
        for value, lower, upper in (
            (Fraction(1, 3), "0.333", "0.334"),
            (Fraction(-1, 3), "-0.334", "-0.333"),
            (Fraction(-1, 10000), "-0.001", "0.000"),
            (Fraction(0), "0.000", "0.000"),
            (Fraction(2), "2.000", "2.000"),
        ):
            self.assertEqual(decimal_bound(value, 3, "lower"), lower)
            self.assertEqual(decimal_bound(value, 3, "upper"), upper)
        record = {"numerator": "-1", "denominator": "3"}
        self.assertEqual(decimal_bound(record, 0, "lower"), "-1")
        self.assertEqual(decimal_bound(record, 0, "upper"), "0")

    def test_decimal_helper_bounds_and_invalid_rational_refused(self):
        for places in (-1, 1001, True, 1.0):
            with self.assertRaises(VerificationError):
                decimal_bound(Fraction(1, 3), places)
        for value in (
            1.0,
            {"numerator": "1", "denominator": "0"},
            {"numerator": "1", "denominator": "-3"},
            {"numerator": "01", "denominator": "3"},
            {"numerator": "2", "denominator": "6"},
            {"numerator": "0", "denominator": "2"},
        ):
            with self.assertRaises(VerificationError):
                decimal_bound(value)
        with self.assertRaises(VerificationError):
            decimal_bound(Fraction(1), direction="nearest")

    def test_large_bounded_decimal_does_not_change_process_digit_limit(self):
        import sys

        limit = (
            sys.get_int_max_str_digits()
            if hasattr(sys, "get_int_max_str_digits")
            else None
        )
        record = {"numerator": "1" + "0" * 4095, "denominator": "1"}
        self.assertEqual(
            decimal_bound(record, 1000, "upper"), record["numerator"] + "." + "0" * 1000
        )
        self.assertEqual(
            decimal_bound(Fraction(1, 10**1000), 1000, "lower"), "0." + "0" * 999 + "1"
        )
        if limit is not None:
            self.assertEqual(sys.get_int_max_str_digits(), limit)


if __name__ == "__main__":
    unittest.main()
