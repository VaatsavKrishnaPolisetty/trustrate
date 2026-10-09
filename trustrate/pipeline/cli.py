"""Download/build/train/evaluate commands. Evaluation never trains or saves a model."""
import argparse
import json
from pathlib import Path

from .data import download_public, load_reviews, make_dataset, write_jsonl
from .models import TrustRateModel
from .validation import evaluate_model


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
    if args.command in ("data", "build"):
        sources, provenance = download_public(Path(args.input).parent)
        rows = make_dataset(sources, args.seed)
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
