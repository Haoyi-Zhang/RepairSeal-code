"""Benign input-selection and finite semantic regressions; no native C runs."""
from __future__ import annotations

import itertools
import math
import random
import unittest

from holdout_differential import (
    BOUNDARY_VALUES, CAMPAIGN_SEED, MASK, VARIANTS,
    canonical, case, oracle, select_domain,
)
from proof_dag_checker import check, evaluate_topological, validate_request_fields
from proof_dag_producer import produce
from refutation_witness_checker import check as compact_check
from refutation_witness_producer import produce as compact_produce


class BoundarySelectionTests(unittest.TestCase):
    def test_every_previously_sampled_value_preserves_boundaries(self):
        for sampled in (2, 7, 15, 31, 0x7FFFFFFF, MASK):
            with self.subTest(sampled=sampled):
                axis = select_domain([0, 1, 3, sampled])
                self.assertEqual(len(axis), 8)
                self.assertEqual(axis, sorted(set(axis)))
                self.assertTrue(set(BOUNDARY_VALUES) <= set(axis))
                self.assertEqual(axis[:3], [0, 1, 2] if sampled == 2 else [0, 1, 3])

    def test_order_duplicates_and_repeated_selection_are_deterministic(self):
        values = [0, 1, 2, 3, 7, 15, *BOUNDARY_VALUES]
        expected = [0, 1, 2, *BOUNDARY_VALUES]
        rng = random.Random(87)
        for _ in range(40):
            rng.shuffle(values)
            self.assertEqual(select_domain(values + values), expected)
            self.assertEqual(select_domain(select_domain(values)), expected)

    def test_400_seeded_requests_have_exact_bounded_products(self):
        point_counts = {64: 0, 512: 0, 4096: 0}
        for index in range(400):
            seed = CAMPAIGN_SEED + index * 104729
            variant = VARIANTS[index % 4]
            request, *_ = case(seed, variant)
            repeated, *_ = case(seed, variant)
            self.assertEqual(canonical(request), canonical(repeated))
            domains, names = validate_request_fields(request)
            self.assertEqual(names, list(("x", "y", "z", "t")[:len(names)]))
            for axis in domains.values():
                self.assertEqual(len(axis), 8)
                self.assertTrue(set(BOUNDARY_VALUES) <= set(axis))
            points = math.prod(map(len, domains.values()))
            self.assertLessEqual(points, 4096)
            point_counts[points] += 1
        self.assertEqual(point_counts, {64: 125, 512: 133, 4096: 142})

    def test_all_four_status_classes_agree_on_corrected_axes(self):
        for index, variant in enumerate(VARIANTS):
            request, original, candidate, reference = case(CAMPAIGN_SEED + index * 104729, variant)
            expected = oracle(request, original, candidate, reference)
            cert = produce(request)
            full = check(request, cert)
            direct = evaluate_topological(request)
            for result in (full, direct):
                self.assertEqual(result["status"], expected["status"])
                self.assertEqual(result["witness"], expected["witness"])
            self.assertEqual(full["checked_cells"], direct["checked_cells"])
            if variant != "accept":
                compact = compact_check(request, compact_produce(request, expected["witness"]))
                self.assertEqual(compact["witness"], expected["witness"])

    def test_simple_boundary_arithmetic_matches_literal_word_formulas(self):
        axis = select_domain([0, 1, 3, MASK])
        source = ("unsigned f(unsigned x, unsigned y) { "
                  "unsigned r = (x + 1u) ^ (x >> (y & 31u)); return r; }")
        request = {"id": "boundary-arithmetic", "word_bits": 32,
                   "inputs": {"x": axis, "y": axis},
                   "original": source, "candidate": source, "reference": source,
                   "repair_guard": "x == 0u"}
        cert = produce(request)
        output = cert["nodes"][cert["role_roots"]["candidate"]["output"]]["vector"]
        self.assertEqual(output, [((x + 1) & MASK) ^ (x >> (y & 31))
                                  for x, y in itertools.product(axis, axis)])
        self.assertEqual(check(request, cert)["status"], "ACCEPT")
        self.assertEqual(evaluate_topological(request)["status"], "ACCEPT")


if __name__ == "__main__":
    unittest.main()
