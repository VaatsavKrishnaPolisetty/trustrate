# TrustRate v3 — release evidence

Active model: `trustrate-uci-v3-56bd58d47f05` (4 qubits, 32 quantum training rows).
Native app: http://127.0.0.1:8080/index.php. Database, API and worker are running.
Administrator credentials stay in `db/.local/compose.env`; no keys are in Git.

## Completed demo-critical flow

- PHP registration/login, CSRF and session protections, ownership enforcement.
- Persistent MySQL reviews, revision-safe edit/rescore/delete, remove/restore/watch
  and audit history; the FastAPI database account has no write privileges.
- Actual public UCI Amazon text, explicit synthetic behavior labels and provenance.
- Exact ten-feature causal extraction, genuine-only preprocessing/training,
  fixed validation calibration, real classical models and Qiskit Aer kernel.
- A1 bot ring, A2 one-star bombing, A3 low-and-slow, A4 new-account subnet farm;
  N1/N2 benign controls. No button supplies fabricated scores.
- Safe product-scoped reset: only button-injected demo rows with injection audit
  records are soft-deleted; imported/user data and audit evidence are retained.
- Models page with measured tables, ROC/PR curves, actual circuit, guard explanation,
  immutable hardware proof and model-version distinction.
- Authenticated asynchronous batch API and persisted job polling. Admin UI supports
  local device-noise experiments and optional quota-consuming IBM experiments.
- Explicit fallback: cached device-noise Aer, otherwise labeled ideal Aer. Failed
  IBM IDs/cancellation attempts remain visible; restart never resubmits uncertain jobs.
- Offline `docs/backup.html`, generated only from measured artifacts. Not a video.

## Data and evaluation v3

2,208 rows: 1,944 genuine-behavior + 264 synthetic attacks. Split sizes:
1,216 train / 496 validation / 496 test. UCI text groups are split-disjoint.
Correcting attack definitions changed the dataset. These numbers **cannot be used
as a direct improvement comparison** against the archived v2 benchmark.

The predictor does not inspect scenario IDs, fraud labels or review IDs to decide.
Genuine-training feature tails supply a separate two-group operational guard.
Classical models use full standardized features; the smaller quantum model uses
PCA. This is not an equal-information/kernel-only comparison.

| Component | Held-out recall | Held-out FPR |
|---|---:|---:|
| Isolation Forest | 31.82% | 0/408 |
| Classical OCSVM, full features | 81.82% | 2/408 |
| Quantum OCSVM, PCA + Aer | 0% | 14/408 |
| Unguarded hybrid | 0% | 5/408 |
| Operational guard + hybrid ranking | 44.32% | 0/408 |

Guarded test precision: 100%; F1: 0.6142, **on this synthetic-behavior test only**.
Scenario outcomes: A1 29/40, A2 7/16, A3 0/16, A4 3/16 detected;
N1 and N2 each 0/24 false positives. Validation guard recall 32.95%, FPR 0/408.
Selection used validation only; the test evaluation was not followed by retuning.

Quantum weight is 0.5 before the separate guard. At threshold 0.5, guard eligibility
determines alerts and quantum affects rankings. **No detection improvement due to
quantum computation is demonstrated.** The stronger classical baseline is displayed.

## IBM proof is deliberately versioned

The retained v2 experiment: `db4ia6qmb58s73898ebg`, `ibm_marrakesh`, DONE,
153 fidelity circuits, 256 shots, 4 qubits, 12 train + 6 demonstration points.
Retrieved kernel MAE vs identical Aer input: 0.014714878151626894.
It proves actual quantum-kernel execution—not a new hardware run of v3.
Original v2 model/data/metrics snapshots are stored under
`service/artifacts/v2-baseline/` with hashes; the hardware receipt is unchanged.

## Checks

- 21 ML correctness tests (including metadata-blind inference and poisoned-held-out
  refit invariance); genuine-only training and saved-model/batch parity.
- 2 isolated PHP lifecycle/security/race tests.
- 1 HTTP demo/reset-boundary test.
- 3 real-service tests, including actual noisy-Aer asynchronous execution and
  PHP → MySQL → Aer → worker → persisted score → moderation/edit/delete.
- 4 job/fallback tests, including forced IBM failure with actual cached-noise
  execution and explicitly labeled ideal Aer when the noise cache is unavailable.
- 1 immutable hardware-evidence test.
- PHP lint and Python compilation; Docker is not installed here and not verified.

New asynchronous IBM submission plumbing has not been exercised with another paid/
quota-consuming job. The prior actual kernel experiment and local noise/fallback
checks are separate evidence; do not confuse them.

## Remaining limitations, not hidden TODO claims

Low-and-slow and many account-farm reviews are missed. No real-world fraud accuracy,
production security certification, quantum advantage, or physical-device visual
testing is claimed. Native HTTP is loopback development only. A recorded video is
not supplied; the offline evidence page is the backup. The application is suitable
for demonstrating the implemented research workflow, not automated real-customer
fraud decisions or a claim that every original PRD acceptance criterion passed.
