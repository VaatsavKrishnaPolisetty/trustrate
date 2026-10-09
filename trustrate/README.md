# TrustRate — reviews, with evidence

A PHP/MySQL review application with a read-only FastAPI model service, real
Isolation Forest / classical OCSVM / Qiskit fidelity-kernel OCSVM inference,
validation-calibrated fusion, and an independently recorded IBM hardware experiment.

**Status:** the local end-to-end release works, including safe demo reset and
asynchronous backend experiments. This is research software, not a production
fraud detector. v3's guarded held-out result detects 29/40 bot-ring reviews with
0/24 false positives in each benign trap; low-and-slow attacks remain missed.
No quantum advantage is demonstrated. See [current release evidence](docs/RELEASE.md).

## Open the running app on this Mac

- Product and sign-in: **http://127.0.0.1:8080/index.php**
- Moderation: **http://127.0.0.1:8080/admin.php** (administrator login required)
- Models, curves and IBM evidence: **http://127.0.0.1:8080/models.php**
- Service health: http://127.0.0.1:8001/health

The old static preview on port 4173 is obsolete. Do not serve PHP files with
`python -m http.server`; use the PHP server below.

The generated administrator email/password are in **`db/.local/compose.env`**.
Read `ADMIN_EMAIL` and `ADMIN_PASSWORD` locally; never publish this file. Ordinary
accounts can register on the product page. Seeded dataset accounts cannot log in.

## Reproduce locally (macOS)

Requirements: Python 3.11, PHP 8.3+ with PDO MySQL/cURL, MySQL server binaries.
Run commands from this README's folder (`trustrate/` inside the current repository).

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pipeline.cli build --qubits 4 --n-train 32
php db/native.php start
php db/run.php init
php db/run.php import
php db/run.php activate-dataset
.venv/bin/python -m service.local start
SCORING_URL=http://127.0.0.1:8001 php db/run.php backfill
```

`native.php` creates a dedicated loopback-only MySQL instance on **13306**, with
data and private configuration under `db/.local/`. It does not change the host's
existing MySQL service. Skip native startup if this dedicated instance is running.
Import is idempotent using source IDs. Backfill uses the real batch scoring API;
PHP validates revisions and writes scores. A background PHP worker handles new
reviews and retries unavailable scoring without blocking review submission.

```bash
.venv/bin/python -m service.local status
.venv/bin/python -m service.local stop
php db/native.php stop
```

Stopping retains database contents. Restart with `native.php start` and
`service.local start`; no reimport/retraining is needed.

## Data and model truth

- Actual public text: UCI **Sentiment Labelled Sentences**, Amazon subset,
  [CC BY 4.0](https://archive.ics.uci.edu/dataset/331/sentiment+labelled+sentences).
- 1,000 source sentences, explicitly reused within—but not across—split groups.
- Generated v3 dataset: **2,208 reviews**, **1,944 genuine-behavior**, **264 attacks**.
- Products, accounts, ratings, timestamps, networks and fraud ground truth are
  synthetic. Sentiment is **not** a fraud label; public authors are not accused.
- Ten causal features use only strictly earlier events; vocabulary/statistics,
  scalers and PCA fit genuine training only. Evaluation loads the saved model
  without retraining or recalibrating on the test split.
- IF and classical OCSVM use all genuine training points and full features.
  Quantum OCSVM uses 32 genuine points and PCA/angle input. These are different
  information/training budgets, not an isolated kernel-only comparison.
  Live scoring evaluates the actual Aer
  fidelity kernel against support vectors, not a weighted fake “quantum score”.
- Validation-only selection chose **50% classical ensemble / 50% quantum** before
  an explicit, separate two-signal operational guard. The guard determines alert
  eligibility at the current threshold; quantum affects ranking only. Both guarded
  and unguarded results appear in the Models page, without an advantage claim.

See [current release](docs/RELEASE.md) and [historical v2 evidence](docs/VERIFICATION.md).
Artifacts and downloaded data are ignored; regenerate them with the build command.
Four qubits are the live default; six-qubit training is supported and smoke-tested.

## IBM hardware — explicit, asynchronous and resumable

The completed **kernel**, not the earlier one-qubit smoke test:

| Item | Result |
|---|---|
| Backend | `ibm_marrakesh` |
| Job | `db4ia6qmb58s73898ebg` |
| Status | DONE, result retrieved |
| Circuits | 153 compute-uncompute fidelity circuits |
| Qubits / shots | 4 / 256 |
| Training / test points | 12 / 6 (small stratified experiment) |
| Kernel mean absolute difference vs Aer | 0.0147148782 |

Credentials stay in local `.env`; the Python scoring API does **not** read them.
Runtime **0.36.1** uses `channel="ibm_cloud"` for the current platform. Do not
restore `ibm_quantum` or `auth.quantum.ibm.com`; that old endpoint is retired.

```bash
# Only for a NEW experiment; consumes IBM quota. Existing receipts prevent duplicates.
.venv/bin/python -m pipeline.hardware_demo submit --n-train 12 --shots 256
# Read status/result of the existing job; never submits another one:
.venv/bin/python -m pipeline.hardware_demo collect
```

The receipt above belongs to v2, not the latest v3 model; its immutable artifacts
are preserved. Hardware and Aer results remain separate. Live customer requests
use Aer. Admins can now launch an explicit asynchronous experiment from Models
or POST `/v1/score/batch` with `async=true`, 1–4 IDs and `mode=ibm`, `aer_noise`, or
`ibm_with_fallback`. Poll GET `/v1/jobs/{job_id}` with the server API key.
Fallback uses a cached device noise model when available; otherwise it explicitly
labels ideal Aer. It never calls a simulator result IBM hardware. Backend
experiments retain Aer calibration and do not overwrite live moderation scores.
An ambiguous
submission is inspected in IBM Workloads before any retry. The six-row experiment
is not statistically comparable to the full 472-row software benchmark.

## Security and review lifecycle

PHP owns database writes. FastAPI uses SELECT-only credentials and a generated
server-side API key, never exposed in browser JS. Sessions have CSRF protection,
regenerated IDs, HttpOnly/SameSite cookies, idle/absolute expiry, role/ownership
checks, and persisted rate limits. PDO uses prepared statements; output is escaped.
IP identities are HMAC hashes with masked prefixes; forwarded headers are ignored.

- Creation/edit: published visibly as `pending_score`, excluded from Genuine.
- Scoring: `published` (genuine/model-watch) or `flagged` (suspicious).
- Remove: excluded from both ratings; restore: explicitly included in Genuine.
- Administrator Watch: excluded from Genuine until restored.
- Delete: soft-deleted, excluded from both ratings and cannot be restored.
- Edits increment revision; stale score responses cannot overwrite current data.
- Moderation actions are recorded with actor, reason, previous state and timestamp.

Native HTTP is loopback development only. Use HTTPS and `COOKIE_SECURE=1` before
external deployment, and perform an independent security review. This is not a
complete production security certification or a retention/privacy compliance policy.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -p test_ml.py -v
.venv/bin/python -m unittest discover -s tests -p test_hardware.py -v
.venv/bin/python -m unittest discover -s tests -p test_jobs.py -v
TRUSTRATE_TEST_DEMO=1 .venv/bin/python -m unittest discover -s tests -p test_demo.py -v
# Stop the live worker to isolate fixture-based race tests:
.venv/bin/python -m service.local stop
TRUSTRATE_START_WEB=1 .venv/bin/python -m unittest discover -s tests -p test_web.py -v
.venv/bin/python -m service.local start
TRUSTRATE_LIVE=1 .venv/bin/python -m unittest discover -s tests -p test_service.py -v
```

The first web suite uses a clearly labeled scoring fixture to force races. The
last suite uses **the real model service and PHP worker**, creates a review,
checks persisted Aer results, moderates, edits and deletes it. Test accounts and
soft-deletion audit records may remain in this development database.

## Docker alternative

Compose wiring is provided but **not runtime-verified here** (Docker unavailable).
Generate configuration with `php db/setup.php`, train local artifacts, then:

```bash
docker compose --env-file db/.local/compose.env up --build -d
docker compose --env-file db/.local/compose.env exec web php /var/www/db/import.php
docker compose --env-file db/.local/compose.env exec web php /var/www/db/backfill.php
```

Compose serves PHP on 4173 and keeps MySQL/FastAPI off host public ports. It mounts
model artifacts read-only. `.dockerignore` excludes private keys/config/data/venv.

## Demo controls and remaining limits

Moderation's demo laboratory supports A1–A4 and N1/N2. Reset affects only the
selected product's button-injected reviews with matching injection audit records.
It preserves imported data, ordinary reviews, original scores and audit history.
The old v2 imported rows are archived with retained scores, not silently deleted.

`python -m pipeline.export_evidence` produces **`docs/backup.html`**, a self-contained
offline evidence page. It is not a recorded video. No backup video is claimed.

Low-and-slow attacks and many account-farm reviews are still missed. Classical
OCSVM outperforms the guarded hybrid. v3's revised scenario data is not directly
comparable with v2. Hardware is a completed v2 experiment; v3 has no new hardware
benchmark. Experimental IBM batch routes are implemented but have not been
exercised with another quota-consuming submission; noise and forced-failure
fallback paths have actual tests. Docker/production deployment and physical-device
visual/accessibility checks remain unverified. Related metadata is not causal
proof of fraud, and no automatic removal should be enabled for real customers.
