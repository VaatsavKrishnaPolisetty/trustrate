# TrustRate — reviews, with evidence

A PHP/MySQL review application with a read-only FastAPI model service, real
Isolation Forest / classical OCSVM / Qiskit fidelity-kernel OCSVM inference,
validation-calibrated fusion, and an independently recorded IBM hardware experiment.

**Status:** the local end-to-end flow works and has integration tests. This is
research software, not a production fraud detector. The shared-NAT false-positive
trap and low-and-slow attack acceptance criteria are **not met**. Do not call a
flag proof of fraud, claim quantum advantage, or deploy this to real shoppers yet.

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
.venv/bin/python -m pipeline.cli build --qubits 4 --n-train 24
php db/native.php start
php db/run.php init
php db/run.php import
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
- Generated dataset: **2,136 reviews**, **1,944 genuine-behavior**, **192 attacks**.
- Products, accounts, ratings, timestamps, networks and fraud ground truth are
  synthetic. Sentiment is **not** a fraud label; public authors are not accused.
- Ten causal features use only strictly earlier events; vocabulary/statistics,
  scalers and PCA fit genuine training only. Evaluation loads the saved model
  without retraining or recalibrating on the test split.
- IF uses all genuine training points. Classical OCSVM and quantum OCSVM share
  24 training points and PCA/angle input. Live scoring evaluates the actual Aer
  fidelity kernel against support vectors, not a weighted fake “quantum score”.
- Validation-only fusion selected **90% classical ensemble / 10% quantum**.

See [methodology](docs/ml-pipeline.md) and [measured evidence](docs/VERIFICATION.md).
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

Hardware and Aer results remain separate. Live customer requests use Aer; hardware
is not synchronous serving and no automatic fallback is claimed. An ambiguous
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

## Remaining acceptance gaps

- NAT false positives and low-and-slow misses require further **validation-only**
  model development; do not tune repeatedly against the reported test results.
- A2/A4 fixture mechanisms currently differ from the PRD's precise review-bombing
  and account-farm definitions (documented); no claim of exact parity.
- IBM hardware runs through a CLI job receipt, not a web-triggered batch jobs API.
- No automatic IBM→noise-model fallback, full text-cluster graph, reset-to-baseline
  control, backup video, or production deployment verification yet.
- Related-review metadata leads and tokenized text analysis are not causal model
  explanations. Performance beyond the small development dataset is unmeasured.
