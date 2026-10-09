"""Frozen validation ECDFs, tie-safe thresholds, and honest held-out metrics."""
import numpy as np
from sklearn.metrics import (average_precision_score, confusion_matrix,
                             precision_recall_fscore_support, roc_auc_score)


def ecdf(reference, values):
    reference = np.asarray(reference, dtype=float)
    if not len(reference) or not np.isfinite(reference).all():
        raise ValueError("A finite nonempty calibration reference is required")
    return np.searchsorted(np.sort(reference), values, side="right") / len(reference)


def calibrate(scores, labels, max_fpr=.05):
    scores, labels = np.asarray(scores, dtype=float), np.asarray(labels)
    normal = np.sort(scores[labels == 0])
    if not len(normal) or not np.isfinite(scores).all() or not 0 <= max_fpr < 1:
        raise ValueError("Finite genuine validation scores and 0 <= max_fpr < 1 required")
    allowed = int(np.floor(max_fpr * len(normal)))
    # Prediction uses STRICT >. At ties this conservatively flags fewer rows.
    threshold = float(normal[len(normal) - allowed - 1])
    return {"threshold": threshold, "comparison": ">", "max_fpr": max_fpr,
            "genuine_count": len(normal), "false_positive_rate": float(np.mean(normal > threshold))}


def fuse_scores(scores, quantum_weight):
    classical_mean = (scores["isolation_forest"] + scores["classical_ocsvm"]) / 2
    return (1 - quantum_weight) * classical_mean + quantum_weight * scores["quantum_ocsvm"]


def guarded_score(fused, guard):
    """Explicit operational layer, separate from the unguarded novelty score."""
    return np.where(guard, .5 + .5 * fused, .49 * fused)


def constrained_calibrate(scores, labels, slices=(), max_fpr=.025, floor=None):
    result = calibrate(scores, labels, max_fpr)
    threshold = result["threshold"]
    for mask in slices:
        if np.any(np.asarray(mask) & (np.asarray(labels) == 0)):
            threshold = max(threshold, calibrate(np.asarray(scores)[mask], np.asarray(labels)[mask], .05)["threshold"])
    if floor is not None:
        threshold = max(threshold, floor)
    result.update(threshold=float(threshold), false_positive_rate=float(np.mean(np.asarray(scores)[np.asarray(labels) == 0] > threshold)))
    result["slice_false_positive_rates"] = [float(np.mean(np.asarray(scores)[np.asarray(mask) & (np.asarray(labels) == 0)] > threshold)) for mask in slices]
    return result


def select_fusion(validation_scores, validation_labels, guard=None, slices=()):
    """Four predeclared candidates, selected solely using validation labels."""
    labels = np.asarray(validation_labels)
    attacks = labels == 1
    candidates = []
    for weight in (.1, .25, .5, .75):
        fused = fuse_scores(validation_scores, weight)
        if guard is not None:
            fused = guarded_score(fused, guard)
        calibration = constrained_calibrate(fused, labels, slices, floor=.5 if guard is not None else None)
        recall = float(np.mean(fused[attacks] > calibration["threshold"])) if attacks.any() else 0.0
        candidates.append({"quantum_weight": weight, "validation_recall": recall, **calibration})
    chosen = min(candidates, key=lambda c: (-c["validation_recall"], abs(c["quantum_weight"] - .5), c["quantum_weight"]))
    return {"chosen_quantum_weight": chosen["quantum_weight"], "candidates": candidates,
            "selection_split": "validation", "attack_count": int(attacks.sum()),
            "rule": "Maximum validation recall at aggregate FPR <=2.5% and genuine N1/N2 slice FPR <=5%; ties prefer 0.5 then nearest then lower"}


def evaluate(scores, labels, threshold):
    scores, labels = np.asarray(scores, dtype=float), np.asarray(labels, dtype=int)
    predicted = scores > threshold
    p, r, f1, _ = precision_recall_fscore_support(labels, predicted, average="binary", zero_division=0)
    tn, fp, fn, tp = confusion_matrix(labels, predicted, labels=[0, 1]).ravel()
    both = len(np.unique(labels)) == 2
    return {"count": len(labels), "precision": float(p), "recall": float(r), "f1": float(f1),
            "roc_auc": float(roc_auc_score(labels, scores)) if both else None,
            "pr_auc": float(average_precision_score(labels, scores)) if both else None,
            "pr_auc_definition": "average precision", "threshold": float(threshold),
            "comparison": ">", "false_positive_rate": float(fp / (tn + fp)) if tn + fp else None,
            "confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)}}


def evaluate_model(model, rows):
    """Only load-derived prediction; this function never fits or calibrates."""
    from .data import assert_split_integrity
    assert_split_integrity(rows)
    test = [r for r in rows if r["split"] == "test"]
    previous = [r for r in rows if r["split"] != "test"]
    X = model.features.transform(test, history=previous)
    scores = model.scores(X)
    labels = np.array([r["true_label"] for r in test])
    metrics = {name: evaluate(values, labels, model.thresholds[name]) for name, values in scores.items()}
    scenarios = {}
    for scenario in sorted(set(r["scenario"] for r in test)):
        mask = np.array([r["scenario"] == scenario for r in test])
        result = evaluate(scores["hybrid"][mask], labels[mask], model.thresholds["hybrid"])
        result["flag_rate"] = float(np.mean(scores["hybrid"][mask] > model.thresholds["hybrid"]))
        scenarios[scenario] = result
    return {"split": "test", "models": metrics, "scenarios": scenarios,
            "metadata": model.metadata,
            "test_scores": [{"id": row["id"], "scenario": row["scenario"], "true_label": row["true_label"],
                             "label": model.label_score(float(scores["hybrid"][i])),
                             "scores": {name: float(value[i]) for name, value in scores.items()}}
                            for i, row in enumerate(test)],
            "limitation": "Synthetic behavioral labels on real public text; not evidence of real fraud detection or quantum advantage."}
