"""Run with: python -m unittest discover -s tests -p test_ml.py -v.

The artifact integration tests deliberately require a real `pipeline.cli build`.
There is no mocked or synthetic replacement for the Aer scoring backend.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from pipeline.data import assert_split_integrity, load_reviews, text_group
from pipeline.features import FEATURE_NAMES, REASON_DETAILS, FeatureExtractor, preprocess_features, validate_review
from pipeline.models import TrustRateModel, select_normal_support
from pipeline.quantum import make_kernel, support_decision
from pipeline.validation import calibrate, ecdf, evaluate_model, select_fusion

ROOT = Path(__file__).resolve().parents[1]


def example(i=0, **updates):
    row = dict(id=f"r{i}", product_id="p", user_id=f"u{i}", ip_hash="ip",
               ip_prefix="prefix", user_agent="Browser", created_at=100000 + i * 100,
               account_created=0, rating=4, body=f"realistic review number {i}",
               revision=1, scenario="G", true_label=0, split="train")
    row.update(updates)
    return row


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.extractor = FeatureExtractor().fit([example(i) for i in range(30)])

    def test_exact_feature_contract_and_input_order(self):
        self.assertEqual(len(FEATURE_NAMES), 10)
        rows = [example(3), example(1), example(2)]
        actual = self.extractor.transform(rows)
        np.testing.assert_array_equal(actual[:, 0], [2, 0, 1])
        np.testing.assert_array_equal(actual[:, 2], [2, 0, 1])
        chronological = self.extractor.transform(sorted(rows, key=lambda r: r["created_at"]))
        np.testing.assert_allclose(actual, chronological[[2, 0, 1]])

    def test_strict_past_no_equal_or_future_history(self):
        row = example(2)
        past, equal, future = example(1), example(8, created_at=row["created_at"]), example(9)
        clean = self.extractor.transform([row], [past])
        np.testing.assert_array_equal(clean, self.extractor.transform([row], [future, equal, past]))
        revised = {**row, "revision": 2, "rating": 1}
        np.testing.assert_array_equal(self.extractor.transform([revised]), self.extractor.transform([revised], [row]))

    def test_window_boundaries(self):
        row = example(0, created_at=200000)
        history = [example(i + 1, created_at=200000 - seconds, account_created=0)
                   for i, seconds in enumerate([600, 3600, 3601, 86400, 86401])]
        values = self.extractor.transform([row], history)[0]
        np.testing.assert_array_equal(values[:3], [2, 4, 4])

    def test_product_burst_recent_30m_excluded_from_baseline(self):
        row = example(0, created_at=200000)
        history = [example(i + 1, created_at=200000 - seconds)
                   for i, seconds in enumerate([0, 1800, 1801, 86400, 86401])]
        history.append(example(20, created_at=199999, product_id="other-product"))
        # One recent event / half-hour; two baseline events / 23.5 hours.
        # Smoothing adds one event per half-hour bucket to both rates.
        self.assertAlmostEqual(self.extractor.transform([row], history)[0, 4], (2 / .5) / (49 / 23.5))
        self.assertEqual(self.extractor.transform([row])[0, 4], 1)

    def test_similarity_same_product_all_strictly_earlier(self):
        row = example(0, created_at=200000)
        other_product = example(1, body=row["body"], created_at=199900, product_id="other")
        equal = example(2, body=row["body"], created_at=200000)
        future = example(3, body=row["body"], created_at=200001)
        self.assertEqual(self.extractor.transform([row], [other_product, equal, future])[0, 6], 0)
        old_same_product = example(4, body=row["body"], created_at=100000)
        self.assertAlmostEqual(self.extractor.transform([row], [old_same_product])[0, 6], 1)

    def test_account_age_uses_hours(self):
        row = example(0, created_at=200000, account_created=200000 - 7200)
        self.assertAlmostEqual(self.extractor.transform([row])[0, 8], np.log1p(2))

    def test_log_preprocessing_exact_columns_without_mutating_raw_values(self):
        raw = np.array([[0, 1, 3, 7, 15, 2, .9, -2, 8, 4]], dtype=float)
        before = raw.copy()
        actual = preprocess_features(raw)
        np.testing.assert_array_equal(actual[:, :5], np.log1p(raw[:, :5]))
        np.testing.assert_array_equal(actual[:, 5:], raw[:, 5:])
        np.testing.assert_array_equal(raw, before)
        bad = raw.copy()
        bad[0, 4] = -1
        with self.assertRaises(ValueError):
            preprocess_features(bad)

    def test_fusion_grid_validation_constraint_and_tie_preference(self):
        labels = np.array([0] * 100 + [1] * 10)
        values = np.array([.25] * 100 + [.9] * 10)
        components = {name: values for name in ("isolation_forest", "classical_ocsvm", "quantum_ocsvm")}
        result = select_fusion(components, labels)
        self.assertEqual(result["chosen_quantum_weight"], .5)
        self.assertEqual([c["quantum_weight"] for c in result["candidates"]], [.1, .25, .5, .75])
        for candidate in result["candidates"]:
            self.assertEqual(candidate["validation_recall"], 1)
            self.assertLessEqual(candidate["false_positive_rate"], .05)

    def test_rejections(self):
        for updates in ({"rating": float("nan")}, {"rating": 6}, {"rating": True},
                        {"body": " "}, {"created_at": float("inf")},
                        {"account_created": 999999}, {"revision": 0}, {"ip_hash": ""},
                        {"created_at": "2025-01-01T12:00:00"}):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                validate_review(example(**updates))
        with self.assertRaises(ValueError):
            self.extractor.transform([example()], [example(1), example(1)])
        with self.assertRaises(ValueError):
            self.extractor.transform([example(), example()])
        for updates in ({"true_label": 1}, {"split": "validation"}):
            with self.assertRaises(ValueError):
                FeatureExtractor().fit([example(**updates)])

    def test_tfidf_and_statistics_fit_only_training(self):
        before = deepcopy(self.extractor.vectorizer.vocabulary_)
        self.extractor.transform([example(50, body="heldoutuniquetoken completelyunseen", user_agent="new")])
        self.assertEqual(before, self.extractor.vectorizer.vocabulary_)
        self.assertNotIn("heldoutuniquetoken", before)

    def test_ecdf_batch_invariance_and_ties(self):
        reference = [0, 0, 1, 2, 2, 5]
        values = [0, 1.5, 6]
        np.testing.assert_array_equal(ecdf(reference, values), [ecdf(reference, [v])[0] for v in values])
        scores = np.ones(100)
        calibration = calibrate(scores, np.zeros(100))
        self.assertEqual(calibration["false_positive_rate"], 0)
        self.assertEqual(calibration["comparison"], ">")
        self.assertLessEqual(calibrate(np.arange(101), np.zeros(101))["false_positive_rate"], .05)

    def test_deterministic_support_represents_rare_normal_modes(self):
        rng = np.random.default_rng(7)
        ordinary = rng.normal(0, .1, (200, 10))
        rare = rng.normal(10, .1, (8, 10))
        features = np.vstack([ordinary, rare])
        selected = select_normal_support(features, 24)
        np.testing.assert_array_equal(selected, select_normal_support(features, 24))
        self.assertEqual(len(set(selected)), 24)
        self.assertTrue(np.any(selected >= len(ordinary)))


class RealArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = ROOT / "service/artifacts/model.joblib"
        if not cls.path.exists():
            raise RuntimeError("First run python -m pipeline.cli build --qubits 4 --n-train 24")
        cls.model = TrustRateModel.load(cls.path)
        cls.rows = load_reviews(ROOT / "data/reviews.jsonl")

    def test_real_source_split_and_fit_membership(self):
        assert_split_integrity(self.rows)
        self.assertGreaterEqual(sum(r["true_label"] == 0 for r in self.rows), 1500)
        self.assertEqual(self.model.metadata["provenance"]["license"], "CC BY 4.0")
        self.assertEqual(self.model.metadata["provenance"]["source_rows"], 1000)
        fitted = {r["id"] for r in self.rows if r["split"] == "train" and r["true_label"] == 0}
        self.assertEqual(set(self.model.features.fit_ids), fitted)
        self.assertTrue(set(self.model.metadata["quantum_train_ids"]) <= fitted)
        broken = deepcopy(self.rows)
        target = next(r for r in broken if r["split"] == "test")
        target["body"] = broken[0]["body"]
        with self.assertRaisesRegex(ValueError, "leaks"):
            assert_split_integrity(broken)
        target["body"] = "independent heldout sentence"
        target["source_group"] = text_group(target["body"])
        target["created_at"] = broken[0]["created_at"]
        with self.assertRaisesRegex(ValueError, "chronological"):
            assert_split_integrity(broken)

    def test_actual_aer_and_correct_cross_kernel(self):
        from qiskit_aer.primitives import Sampler
        kernel = make_kernel(4)
        self.assertIsInstance(kernel._fidelity._sampler, Sampler)
        angles = self.model.quantum_train[:3] + .0001
        full = kernel.evaluate(angles, self.model.quantum_train)
        expected = self.model.quantum_ocsvm.decision_function(full)
        actual = support_decision(kernel, angles, self.model.quantum_support,
                                  self.model.quantum_dual, self.model.quantum_intercept)
        np.testing.assert_allclose(actual, expected, atol=1e-9, rtol=1e-9)

    def test_v3_scenario_semantics_and_baseline_immutable(self):
        for split in ("train", "validation", "test"):
            rows = [r for r in self.rows if r["split"] == split]
            self.assertTrue(all(r["id"].startswith(f"v3-{split}-") for r in rows))
            attacks = {name: [r for r in rows if r["scenario"] == name] for name in ("A1", "A2", "A3", "A4")}
            self.assertTrue(30 <= len(attacks["A1"]) <= 60)
            self.assertEqual(len({r["ip_hash"] for r in attacks["A1"]}), 5)
            self.assertLess(max(r["created_at"] for r in attacks["A1"]) - min(r["created_at"] for r in attacks["A1"]), 1200)
            self.assertEqual({r["rating"] for r in attacks["A2"]}, {1})
            self.assertLessEqual(len({r["ip_hash"] for r in attacks["A2"]}), 3)
            self.assertEqual(len({r["body"] for r in attacks["A3"]}), len(attacks["A3"]))
            self.assertTrue(all(b["created_at"] - a["created_at"] >= 86400 for a, b in zip(attacks["A3"], attacks["A3"][1:])))
            self.assertEqual(len({r["user_id"] for r in attacks["A4"]}), len(attacks["A4"]))
            self.assertEqual(len({r["ip_prefix"] for r in attacks["A4"]}), 1)
            self.assertTrue(all(r["created_at"] - r["account_created"] <= 3600 for r in attacks["A4"]))
        baseline = ROOT / "service/artifacts/v2-baseline"
        if not baseline.exists():
            # A fresh clone has no previous v2 experiment to preserve.
            return
        manifest = json.loads((baseline / "manifest.json").read_text())
        for name, digest in manifest["sha256"].items():
            self.assertEqual(hashlib.sha256((baseline / name).read_bytes()).hexdigest(), digest)

    def test_predictor_ignores_scenario_labels_and_frozen_guard(self):
        batch = [r for r in self.rows if r["split"] == "validation"][:4]
        history = [r for r in self.rows if r["split"] == "train"]
        changed = [{**r, "scenario": "N1", "true_label": 1 - r["true_label"]} for r in batch]
        X = self.model.features.transform(batch, history)
        np.testing.assert_array_equal(X, self.model.features.transform(changed, history))
        before = deepcopy(self.model.thresholds)
        scores = self.model.scores(X)
        guard = self.model.operational_guard(X)
        expected = np.where(guard, .5 + .5 * scores["hybrid_unguarded"], .49 * scores["hybrid_unguarded"])
        np.testing.assert_array_equal(scores["hybrid"], expected)
        self.assertEqual(before, self.model.thresholds)
        self.assertEqual(self.model.metadata["operational_guard"]["fit_split"], "genuine train")
        self.assertEqual(self.model.metadata["fusion_selection"]["selection_split"], "validation")
        for candidate in self.model.metadata["fusion_selection"]["candidates"]:
            self.assertLessEqual(candidate["false_positive_rate"], .025)
            self.assertTrue(all(rate <= .05 for rate in candidate["slice_false_positive_rates"]))

    def test_heldout_values_cannot_change_fit_or_selection(self):
        # Regression only: same frozen hyperparameters, no test evaluation and
        # no artifact write. Poison every held-out label/text/agent value.
        poisoned = [{**r, "true_label": 1 - r["true_label"],
                     "body": f"heldoutpoisonword unique {r['id']}",
                     "user_agent": "heldoutpoisonagent"} if r["split"] == "test" else r
                    for r in self.rows]
        fitted = TrustRateModel(self.model.qubits, self.model.n_train, self.model.seed).fit(
            poisoned, self.model.metadata["provenance"])
        self.assertEqual(fitted.model_version, self.model.model_version)
        self.assertEqual(fitted.thresholds, self.model.thresholds)
        self.assertEqual(fitted.metadata["fusion_selection"], self.model.metadata["fusion_selection"])
        np.testing.assert_array_equal(fitted.quantum_train, self.model.quantum_train)
        self.assertNotIn("heldoutpoisonword", fitted.features.vectorizer.vocabulary_)

    def test_score_batch_and_load_new_review(self):
        batch = self.rows[-5:]
        X = self.model.features.transform(batch, history=self.rows[:-5])
        together = self.model.scores(X)
        for i in range(len(X)):
            alone = self.model.scores(X[i:i + 1])
            for key in together:
                self.assertEqual(together[key][i], alone[key][0])
        self.assertTrue(np.any(together["hybrid"] > 0))
        review = {**self.rows[-1], "id": "new-unseen-review", "body": "Brand new independently submitted review.",
                  "created_at": self.rows[-1]["created_at"] + 100}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "saved.joblib"
            self.model.save(path)
            loaded = TrustRateModel.load(path)
            before = self.model.score_review(review, self.rows)
            after = loaded.score_review(review, self.rows)
        self.assertEqual(before, after)
        self.assertEqual(after["backend"], "aer_simulator")
        self.assertIn(after["label"], ("genuine", "watch", "suspicious"))
        self.assertEqual(len(after["reasons"]), 3)

    def test_log_preprocessing_train_infer_and_raw_reasons(self):
        train = [r for r in self.rows if r["split"] == "train"]
        raw = self.model.features.transform(train)
        normal = np.array([r["true_label"] == 0 for r in train])
        np.testing.assert_allclose(self.model.scaler.mean_, preprocess_features(raw[normal]).mean(axis=0))
        expected_z = self.model.scaler.transform(preprocess_features(raw[-3:]))
        actual_z, _ = self.model._angles(raw[-3:])
        np.testing.assert_array_equal(actual_z, expected_z)
        review = self.rows[-1]
        raw_review = self.model.features.transform([review], self.rows[:-1])[0]
        result = self.model.score_review(review, self.rows[:-1])
        for reason in result["reasons"]:
            index = FEATURE_NAMES.index(reason["feature"])
            self.assertEqual(reason["value"], raw_review[index])
            self.assertEqual((reason["code"], reason["description"]), REASON_DETAILS[reason["feature"]])
            self.assertEqual(reason["description"], self.model.metadata["reason_code_map"][reason["code"]])

    def test_frozen_watch_threshold_boundaries_and_fusion(self):
        watch = self.model.watch_thresholds["hybrid"]
        suspicious = self.model.thresholds["hybrid"]
        self.assertLess(watch, suspicious)
        self.assertEqual(self.model.label_score(watch), "genuine")
        self.assertEqual(self.model.label_score(np.nextafter(watch, np.inf)), "watch")
        self.assertEqual(self.model.label_score(suspicious), "watch")
        self.assertEqual(self.model.label_score(np.nextafter(suspicious, np.inf)), "suspicious")
        for calibration in self.model.metadata["watch_calibration"].values():
            self.assertLessEqual(calibration["false_positive_rate"], .2)
        selected = self.model.metadata["fusion_selection"]
        self.assertEqual(selected["selection_split"], "validation")
        self.assertIn(self.model.quantum_weight, [.1, .25, .5, .75])
        winning = next(c for c in selected["candidates"] if c["quantum_weight"] == self.model.quantum_weight)
        self.assertEqual(winning["validation_recall"], max(c["validation_recall"] for c in selected["candidates"]))
        for candidate in selected["candidates"]:
            self.assertLessEqual(candidate["false_positive_rate"], .05)

    def test_evaluate_does_not_fit_or_modify_artifact(self):
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        # Retain a small held-out set for speed; every train/validation row is
        # still history. Evaluation must not touch any fit or calibration API.
        rows = [r for r in self.rows if r["split"] != "test"] + self.rows[-3:]
        with patch.object(TrustRateModel, "fit", side_effect=AssertionError("retrained")), \
             patch("pipeline.models.calibrate", side_effect=AssertionError("recalibrated")), \
             patch("pipeline.models.select_fusion", side_effect=AssertionError("retuned fusion")):
            metrics = evaluate_model(TrustRateModel.load(self.path), rows)
        self.assertEqual(metrics["models"]["hybrid"]["count"], 3)
        self.assertEqual(before, hashlib.sha256(self.path.read_bytes()).hexdigest())
        for calibration in self.model.metadata["calibration"].values():
            self.assertLessEqual(calibration["false_positive_rate"], .05)


if __name__ == "__main__":
    unittest.main()
