# Verification and remaining acceptance work

Recorded 2026-10-09. Model `trustrate-uci-v2-9eceba0ec859`.

## Real data / leakage controls

UCI Sentiment Labelled Sentences (dataset 331), Amazon subset, CC BY 4.0.
Source archive SHA-256:
`afc26626d710899948693e1a61405dce197f57ffa719fa1130d346b4cc095343`.
The downloaded license page and source hashes are retained locally in `data/`.
Public text is attributed, not described as verified purchases or labeled fraud.
2,136 generated reviews include 1,944 genuine-behavior and 192 attack rows.
Source text groups are disjoint across chronological splits. Baseline statistics,
TF-IDF, scaler, PCA and feature angles fit genuine training only. Frozen ECDF
references/thresholds and fusion selection use validation, never held-out test.

## Held-out test results (472 rows)

| Model | Precision | Recall | F1 | ROC AUC | PR AUC |
|---|---:|---:|---:|---:|---:|
| Isolation Forest | .6379 | .5781 | .6066 | .9297 | .6398 |
| Classical OCSVM | .6182 | .5313 | .5714 | .8566 | .6823 |
| Quantum OCSVM (Aer) | .1389 | .0781 | .1000 | .6512 | .1844 |
| Hybrid | .6230 | .5938 | .6080 | .8999 | .5692 |

The validation-only weight search selected quantum weight 0.10. Validation FPR
is 4.90%; held-out hybrid FPR is **5.64%**. Shared-NAT N1 has **17/24 false
positives**, and A3 has **0/16 detected**. These are failed quality acceptance
criteria, not successful robustness demonstrations. Improve using new training
and validation experiments; retain this test result as a fixed historical report.

## IBM quantum-kernel evidence

- Job: `db4ia6qmb58s73898ebg`
- Backend: `ibm_marrakesh`
- Status: **DONE**; result fetched and verified, not merely queued
- Four-qubit ZZFeatureMap, one repetition, linear entanglement
- 12 genuine training vectors + 6 stratified demonstration points
- 153 compute-uncompute fidelity circuits; 256 shots each
- Pairwise zero-bitstring frequencies form the measured kernel matrix
- Hardware training kernel used by precomputed-kernel OneClassSVM
- Compared with Aer on identical angle vectors
- Kernel mean absolute difference: **0.014714878151626894**
- Minimum training eigenvalue: **0.3224340203665841**

Local evidence: `service/artifacts/hardware.json`, `hardware-plan.json`,
`hardware-kernel.npy`, `hardware-aer-kernel.npy`, `circuit.txt`.
The experiment is small and stratified, not a full hardware test-set benchmark.
The earlier one-qubit smoke test is not counted as detector verification.

## Checks actually executed

- 17 ML tests: input validation, chronological windows, no equal/future events,
  exact F5/F7/F9 definitions, log preprocessing, disjoint source groups, frozen
  calibration, quantum cross-kernel agreement, batch invariance, saved model
  inference and evaluation without retraining.
- 2 PHP lifecycle tests: CSRF, password/session flow, ownership, stale revisions,
  moderation/audit/rating semantics, read-only database write denial, worker
  response mismatch and edit/restore races, synthetic injections. These use an
  explicit scoring fixture; the live worker is stopped for isolation.
- 2 separate real-service tests: unauthorized/malformed/missing-ID rejection,
  model-score parity with the actual API, batch/single invariance, PHP review
  submission → MySQL → Aer service → PHP worker score persistence, admin
  remove/restore → audit display, edit invalidation, owner deletion.
- 1 saved-hardware evidence test: receipt status, non-placeholder job ID, plan
  checksum, finite symmetric kernel, circuit count, saved Aer comparison and
  finite OCSVM scores. No new hardware job is submitted by this test.
- PHP lint on application/CLI files and Python compilation.
- Native dedicated MySQL and PHP/FastAPI processes exercised on this Mac.
- Six-qubit genuine-only training completed in `.runtime/six-qubit-model.joblib`
  without replacing the four-qubit live artifact.

## Important nonclaims

Docker is configured but unavailable here, so no Docker runtime check is claimed.
Native PHP HTTP is loopback development, not production TLS/security certification.
Browser visual/a11y testing across physical devices has not been completed.
No automatic IBM fallback or background web hardware job API is claimed.
No real-world fraud accuracy, zero-NAT-false-positive outcome, guaranteed stable
Genuine Rating, or quantum advantage is claimed.
