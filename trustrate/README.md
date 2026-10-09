# TrustRate ✦

**Reviews you can trust.** TrustRate is a polished, responsive demo of quantum-classical cyber anomaly detection for the Qiskit Fall Fest hackathon. It catches coordinated review manipulation, explains the signal, and protects a Genuine Rating for shoppers.

## Demo in 3 minutes

Requirements: Python 3.11+ recommended (Qiskit 2.x does not support the host Python 3.9), and any simple static-file server.

```bash
cd trustrate
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn service.app.main:app --reload --port 8000
```

In a second terminal:

```bash
cd trustrate
python3 -m http.server 4173 --directory web
```

Open http://localhost:4173. The live demo pages are:

- `/index.html` — consumer review experience with raw vs Genuine Rating
- `/admin.html` — trust & safety console; click **Simulate bot-ring**
- `/models.html` — benchmark, Qiskit circuit, and IBM Quantum run status

The API docs are at http://localhost:8000/docs.

## IBM Quantum hardware

Copy the safe template and edit it locally. Never commit `.env` or paste the token into chat.

```bash
cp .env.example .env
open -e .env
```

Set `IBM_QUANTUM_TOKEN` and keep `IBM_BACKEND_NAME` blank for automatic selection:

```env
IBM_QUANTUM_TOKEN=your-local-token
IBM_INSTANCE=
IBM_BACKEND_NAME=
QUANTUM_MODE=ibm_with_fallback
```

Run a tiny real hardware smoke test:

```bash
set -a; source .env; set +a
python pipeline/hardware_demo.py
```

The production detector path is designed around `ZZFeatureMap`, `FidelityQuantumKernel`, and a precomputed-kernel scikit-learn `OneClassSVM`, with Aer as the reliable demo backend and an IBM Runtime path for the hardware proof. Current Qiskit APIs are intentionally isolated so the hardware adapter can be upgraded without changing the product UI.

## Architecture

```text
Responsive consumer UI / admin console
                 │ JSON REST
FastAPI scoring service ── classical scores + quantum-kernel score + reason codes
                 │
      Aer simulator / IBM Quantum Runtime
```

The demo ships with deterministic synthetic traffic using documentation-range IPs. This is deliberate: no real addresses or private review data belong in the repository. A full database/PHP deployment can use the same endpoint contract; the demo front end is static so it starts on a clean laptop even before PHP is installed.

## Security and demo notes

- `.env` is ignored and secrets never belong in Git.
- API actions use an API key in the demo; production deployment should put FastAPI behind a private network and a real identity/session layer.
- Review text is escaped before rendering.
- The attack button only injects synthetic data and is safe to reset.
- This is a hackathon demonstration, not a claim of quantum advantage. Benchmark results are labelled and should be rerun before publication.

## Repository layout

```text
service/app/main.py       FastAPI API and hybrid demo scoring
pipeline/hardware_demo.py IBM Quantum Runtime smoke run
web/                      responsive product, admin, and model pages
```
