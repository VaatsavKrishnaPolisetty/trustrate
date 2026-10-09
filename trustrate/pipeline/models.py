"""Persisted causal preprocessing, classical baselines, and Aer novelty model."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import joblib
import numpy as np
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import MinMaxScaler, StandardScaler
from sklearn.svm import OneClassSVM

from .data import assert_split_integrity
from .features import FEATURE_NAMES, REASON_DETAILS, FeatureExtractor, preprocess_features
from .quantum import fit_quantum, make_kernel, support_decision
from .validation import calibrate, ecdf, fuse_scores, select_fusion


class TrustRateModel:
    def __init__(self, qubits=4, n_train=24, seed=42):
        if qubits not in (4, 6) or not 24 <= n_train <= 40:
            raise ValueError("Use 4/6 qubits and 24–40 genuine quantum training rows")
        self.qubits, self.n_train, self.seed = qubits, n_train, seed
        self.backend = "aer_simulator"
        self._kernel = None

    def fit(self, rows, provenance=None):
        """Fit on canonical split-annotated rows; test values never enter fitting."""
        rows = list(rows)
        assert_split_integrity(rows)
        train = [r for r in rows if r["split"] == "train"]
        validation = [r for r in rows if r["split"] == "validation"]
        genuine = [r for r in train if r["true_label"] == 0]
        if len(genuine) < self.n_train:
            raise ValueError("Insufficient genuine training rows")
        self.features = FeatureExtractor().fit(genuine)
        # Attacks can appear in causal history, but never become fit examples.
        train_features = self.features.transform(train)
        normal_mask = np.array([r["true_label"] == 0 for r in train])
        X = train_features[normal_mask]
        preprocessed = preprocess_features(X)
        self.scaler = StandardScaler().fit(preprocessed)
        Z = self.scaler.transform(preprocessed)
        self.pca = PCA(n_components=self.qubits, svd_solver="full").fit(Z)
        P = self._project(Z)
        self.angle_scaler = MinMaxScaler(feature_range=(0, np.pi), clip=True).fit(P)
        angles = self.angle_scaler.transform(P)
        self.isolation_forest = IsolationForest(n_estimators=150, random_state=self.seed, n_jobs=1).fit(Z)
        # Identical points and angle inputs isolate the kernel comparison.
        selected = np.sort(np.random.default_rng(self.seed).choice(len(X), self.n_train, replace=False))
        self.quantum_train = angles[selected].copy()
        self.classical_ocsvm = OneClassSVM(kernel="rbf", gamma="scale", nu=.1).fit(self.quantum_train)
        self._kernel, self.quantum_ocsvm = fit_quantum(self.quantum_train, self.seed)
        self.quantum_support = self.quantum_train[self.quantum_ocsvm.support_].copy()
        self.quantum_dual = self.quantum_ocsvm.dual_coef_.ravel().copy()
        self.quantum_intercept = float(self.quantum_ocsvm.intercept_[0])
        V = self.features.transform(validation, history=train)
        raw = self.raw_scores(V)
        normal_validation = np.array([r["true_label"] == 0 for r in validation])
        if not normal_validation.any():
            raise ValueError("Genuine validation rows are required")
        self.ecdf_references = {name: np.sort(values[normal_validation]) for name, values in raw.items()}
        labels = np.array([r["true_label"] for r in validation])
        components = {name: ecdf(self.ecdf_references[name], values) for name, values in raw.items()}
        fusion_selection = select_fusion(components, labels)
        self.quantum_weight = fusion_selection["chosen_quantum_weight"]
        calibrated = self._normalize(raw)
        calibration = {name: calibrate(value, labels) for name, value in calibrated.items()}
        self.thresholds = {name: result["threshold"] for name, result in calibration.items()}
        watch_calibration = {name: calibrate(value, labels, max_fpr=.2) for name, value in calibrated.items()}
        self.watch_thresholds = {name: result["threshold"] for name, result in watch_calibration.items()}
        fingerprint = hashlib.sha256(json.dumps({"train": train, "validation": validation,
                                                 "seed": self.seed, "qubits": self.qubits,
                                                 "n_train": self.n_train, "pipeline_version": 2,
                                                 "quantum_weight": self.quantum_weight}, sort_keys=True).encode()).hexdigest()
        self.model_version = f"trustrate-uci-v2-{fingerprint[:12]}"
        self.metadata = {
            "model_version": self.model_version, "backend": self.backend,
            "simulator": "qiskit_aer.primitives.Sampler(method=statevector, shots=None)",
            "quantum_fidelity": "ComputeUncompute + FidelityQuantumKernel",
            "qubits": self.qubits, "quantum_train_count": len(self.quantum_train),
            "quantum_support_count": len(self.quantum_support), "classical_ocsvm_train_count": len(selected),
            "genuine_train_count": len(genuine), "genuine_validation_count": int(normal_validation.sum()),
            "quantum_train_ids": [genuine[i]["id"] for i in selected],
            "feature_names": FEATURE_NAMES, "seed": self.seed, "calibration": calibration,
            "threshold": self.thresholds["hybrid"], "watch_threshold": self.watch_thresholds["hybrid"],
            "watch_thresholds": self.watch_thresholds, "watch_calibration": watch_calibration,
            "quantum_weight": self.quantum_weight, "fusion_selection": fusion_selection,
            "hybrid_formula": f"{1 - self.quantum_weight:g} * mean(IF, classical_OCSVM) + {self.quantum_weight:g} * quantum_OCSVM",
            "preprocessing": "log1p(F1–F5), then genuine-training StandardScaler; F6–F10 unchanged before scaling",
            "reason_code_map": {code: description for code, description in REASON_DETAILS.values()},
            "pca_explained_variance": self.pca.explained_variance_ratio_.tolist(),
            "provenance": provenance or {}, "fit_fingerprint": fingerprint,
            "labels": "Synthetic behavior labels; UCI sentiment is not fraud ground truth",
        }
        return self

    def _project(self, Z):
        # Row-wise contraction is independent of request size. It also avoids
        # spurious floating-point status warnings from macOS Accelerate GEMM.
        return np.einsum("ij,kj->ik", Z - self.pca.mean_, self.pca.components_, optimize=False)

    def _angles(self, X):
        Z = self.scaler.transform(preprocess_features(X))
        return Z, self.angle_scaler.transform(self._project(Z))

    def raw_scores(self, X):
        Z, angles = self._angles(X)
        if self._kernel is None:
            self._kernel = make_kernel(self.qubits, self.seed)
        return {
            "isolation_forest": -self.isolation_forest.decision_function(Z),
            "classical_ocsvm": -self.classical_ocsvm.decision_function(angles),
            "quantum_ocsvm": -support_decision(self._kernel, angles, self.quantum_support,
                                               self.quantum_dual, self.quantum_intercept),
        }

    def _normalize(self, raw):
        result = {name: ecdf(self.ecdf_references[name], values) for name, values in raw.items()}
        result["hybrid"] = fuse_scores(result, self.quantum_weight)
        return result

    def scores(self, X):
        """Frozen ECDF normalization: no per-request or per-batch fitting."""
        return self._normalize(self.raw_scores(X))

    def score_review(self, review: dict, history: list[dict]):
        X = self.features.transform([review], history=history)
        scores = {name: float(value[0]) for name, value in self.scores(X).items()}
        standardized = np.abs(self.scaler.transform(preprocess_features(X))[0])
        top = np.argsort(-standardized)[:3]
        reasons = [{"feature": FEATURE_NAMES[i], "value": float(X[0, i]),
                    "code": REASON_DETAILS[FEATURE_NAMES[i]][0],
                    "description": REASON_DETAILS[FEATURE_NAMES[i]][1],
                    "training_z_magnitude": float(standardized[i])} for i in top]
        return {"scores": scores, "label": self.label_score(scores["hybrid"]),
                "reasons": reasons, "backend": self.backend, "model_version": self.model_version,
                "threshold": self.thresholds["hybrid"], "watch_threshold": self.watch_thresholds["hybrid"],
                "comparison": ">"}

    def label_score(self, score):
        if score > self.thresholds["hybrid"]:
            return "suspicious"
        if score > self.watch_thresholds["hybrid"]:
            return "watch"
        return "genuine"

    def __getstate__(self):
        state = self.__dict__.copy()
        state["_kernel"] = None  # reconstruct an explicit Aer primitive on load
        return state

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @classmethod
    def load(cls, path):
        model = joblib.load(path)
        if not isinstance(model, cls) or not hasattr(model, "watch_thresholds"):
            raise ValueError("Unsupported model artifact; rebuild with pipeline.cli build")
        return model
