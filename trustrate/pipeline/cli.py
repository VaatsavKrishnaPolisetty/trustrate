"""Download/build/train/evaluate commands. Evaluation never trains or saves a model."""
import argparse
import json
import hashlib
import shutil
from pathlib import Path

from .data import download_public, load_reviews, make_dataset, write_jsonl
from .models import TrustRateModel
from .validation import evaluate_model


def preserve_v2_baseline(artifact, reviews):
    """Snapshot original evidence before regeneration, never overwrite a baseline."""
    root = Path(artifact).parent
    destination = root / "v2-baseline"
    if destination.exists():
        return
    if not Path(artifact).exists():
        return
    old = TrustRateModel.load(artifact)
    if "-v2-" not in old.model_version:
        return
    destination.mkdir()
    manifest = {}
    for source in [p for p in root.iterdir() if p.is_file()] + [Path(reviews), Path(reviews).parent / "provenance.json"]:
        if source.exists():
            shutil.copy2(source, destination / source.name)
            manifest[source.name] = hashlib.sha256(source.read_bytes()).hexdigest()
    (destination / "manifest.json").write_text(json.dumps({"model_version": old.model_version, "sha256": manifest}, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("data", "build", "train", "evaluate"):
        p = sub.add_parser(command)
        p.add_argument("--input", default="data/reviews.jsonl")
        p.add_argument("--artifact", default="service/artifacts/model.joblib")
        p.add_argument("--metrics", default="service/artifacts/metrics.json")
        p.add_argument("--seed", type=int, default=42)
        p.add_argument("--qubits", type=int, choices=(4, 6), default=4)
        p.add_argument("--n-train", type=int, default=24)
    args = parser.parse_args()
    provenance_path = Path(args.input).parent / "provenance.json"
    if args.command in ("data", "build", "train"):
        preserve_v2_baseline(args.artifact, args.input)
    if args.command in ("data", "build"):
        sources, provenance = download_public(Path(args.input).parent)
        rows = make_dataset(sources, args.seed)
        provenance["dataset_methodology"] = "v3: corrected A1 five-IP 40-review/20-minute burst; A2 one-star few-IP bombing; A3 unique public text day-scale campaign; A4 many new accounts once on shared subnet. Synthetic fraud labels. v2 metrics not directly comparable."
        provenance["dataset_namespace"] = "v3-{split}-{serial}"
        provenance_path.write_text(json.dumps(provenance, indent=2) + "\n")
        write_jsonl(rows, args.input)
        print(f"Generated {len(rows)} rows from 1000 real Amazon sentences; synthetic behavior labels", flush=True)
        if args.command == "data":
            return
    else:
        rows = load_reviews(args.input)
        provenance = json.loads(provenance_path.read_text()) if provenance_path.exists() else {}
    if args.command in ("train", "build"):
        print("Fitting genuine-only transforms and explicit Aer quantum kernel...", flush=True)
        model = TrustRateModel(args.qubits, args.n_train, args.seed).fit(rows, provenance)
        model.save(args.artifact)
        print(f"Saved {args.artifact}: {model.model_version}", flush=True)
        if args.command == "train":
            return
    # Deliberately load even after build, exercising the actual serving artifact.
    model = TrustRateModel.load(args.artifact)
    metrics = evaluate_model(model, rows)
    path = Path(args.metrics)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metrics, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"artifact": args.artifact, "metrics": args.metrics,
                      "models": metrics["models"], "scenarios": metrics["scenarios"]}, indent=2))


if __name__ == "__main__":
    main()
