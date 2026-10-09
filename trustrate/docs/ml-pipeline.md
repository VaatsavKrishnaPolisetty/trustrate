# Reproducible ML pipeline

The pipeline deliberately uses public-style, non-identifying fields and can be
run without network access or IBM credentials. `data` creates a deterministic
fixture that has the same schema as an imported review export; it is not a
claim about a real marketplace dataset.

```bash
python -m pipeline.cli data --out data/reviews.jsonl --seed 42
python -m pipeline.cli import https://example.org/reviews.csv --out data/public.csv --provenance data/public.provenance.json --license CC-BY-4.0
python -m pipeline.cli train --input data/reviews.jsonl --artifact artifacts/model.joblib
python -m pipeline.cli evaluate --input data/reviews.jsonl --artifact artifacts/model.joblib
# optional local Qiskit kernel (slower): add --quantum to train
```

For a public-style import, download a review dataset from its official
repository (for example a Kaggle/academic export), obtain any required
license, and convert it to JSONL/CSV with columns `user,rating,body,ip,ua,
timestamp,label`. Keep raw downloads outside Git and document URL, version,
license, and SHA-256 in your experiment log. IPs should be pseudonymized before
import; the fixture uses RFC 5737 documentation ranges.

The PRD features F1-F10 are defined in `pipeline/features.py`; extraction is
chronological and uses only prior events, preventing future leakage. Models and scaler are
persisted together with joblib. The quantum path uses Qiskit's
`FidelityQuantumKernel` and a precomputed-kernel `OneClassSVM`; it is local and
does not submit IBM jobs. `pipeline/hardware_demo.py` remains the explicit,
credential-gated IBM adapter.
