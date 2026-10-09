# TrustRate ML/data pipeline

## Run the complete experiment

From the `trustrate` directory, using the pinned Python environment:

```bash
.venv/bin/python -m pipeline.cli build --qubits 4 --n-train 24
.venv/bin/python -m pipeline.cli evaluate
.venv/bin/python -m unittest discover -s tests -p test_ml.py -v
```

`build` downloads/caches the official source, generates metadata, trains, saves,
**reloads the saved model**, and evaluates the chronological held-out test split.
`evaluate` only loads and predicts; it never fits, recalibrates, or saves a model.
`data` performs acquisition/generation only; `train` uses an existing dataset and
saves without test evaluation. Options: `--input data/reviews.jsonl`,
`--artifact service/artifacts/model.joblib`, `--metrics service/artifacts/metrics.json`,
`--seed 42`, `--qubits {4,6}`, and `--n-train` from 24 through 40.
The tested complete run uses four qubits and 24 training points. Six-qubit
configuration is supported but is not the reported benchmark.

Outputs:

- `data/sentiment-labelled-sentences.zip`: unmodified official public archive.
- `data/uci-331.html`: original license-page evidence.
- `data/provenance.json`: attribution, URLs, license verification, retrieval time,
  archive/member/page SHA-256 hashes.
- `data/reviews.jsonl`: canonical annotated synthetic-behavior dataset.
- `service/artifacts/model.joblib`: learned text/statistical transforms, PCA,
  angle scaler, models, quantum training/support points, fixed validation ECDFs,
  thresholds, and metadata.
- `service/artifacts/metrics.json`: held-out metrics, confusion counts,
  per-scenario results, and every held-out review's scores.

Raw/generated `data/` and generated `service/artifacts/` are local outputs and
must be ignored by Git. Source files do not contain the public review corpus.

## Public source and label limitations

Source: [UCI Sentiment Labelled Sentences, dataset 331](https://archive.ics.uci.edu/dataset/331/sentiment+labelled+sentences).
The official page explicitly licenses the dataset **CC BY 4.0**. Acquisition
checks that assertion in the downloaded page, rather than accepting a supplied
license string. Download: <https://archive.ics.uci.edu/static/public/331/sentiment+labelled+sentences.zip>.

Attribution: Kotzias, D. (2015). *Sentiment Labelled Sentences*. UCI Machine
Learning Repository. DOI: [10.24432/C57604](https://doi.org/10.24432/C57604).
Underlying paper: Kotzias, Denil, de Freitas, and Smyth, *From Group to Individual
Labels Using Deep Features*, KDD 2015. License:
<https://creativecommons.org/licenses/by/4.0/>.

Verified archive SHA-256:
`afc26626d710899948693e1a61405dce197f57ffa719fa1130d346b4cc095343`.
Amazon member SHA-256:
`47003fc0a0d4840b00e96e715b6189bad09e7443a3da41c4cbe12ffc79f86ae3`.

The Amazon member has 1,000 actual public sentences. **Positive/negative
sentiment is not fraud ground truth.** Sentiment only makes synthetic star
ratings plausible (positive: 4–5; negative: 1–3). Accounts, products, timestamps,
IP hashes/prefixes, user agents, scenario membership, and `true_label` are all
synthetic. Public text remains verbatim. The generator intentionally reuses
sentences to obtain 1,800 baseline genuine-behavior examples plus genuine traps;
these are not 1,800 independently observed real reviews.

Normalized exact-text hashes group duplicates before a seeded 60/20/20 source
allocation. Groups belong to one split only. Source-row/group annotations make
reuse auditable. The complete generated dataset represents 981 distinct
normalized source text groups; reserved but unused attack texts are omitted.
Campaign text pools and `template_group` identifiers are split-specific; no
attack slogan/template is shared across splits. The same attack *mechanisms*
recur so the experiment evaluates new texts/accounts executing those mechanisms,
not transfer to entirely unseen attack mechanisms.

| Split | Baseline G | Genuine N1/N2 | Attacks A1–A4 | Total |
|---|---:|---:|---:|---:|
| Train | 1,080 | 48 | 64 | 1,192 |
| Validation | 360 | 48 | 64 | 472 |
| Test | 360 | 48 | 64 | 472 |

There are **1,944 genuine-behavior and 192 attack rows**. Each split is a later
time interval, separated by two days. Split validation rejects overlapping
chronology, duplicate IDs, and cross-split body/source/template groups. No test
scores influence data generation, parameters, thresholds, or training selection.

### Scenarios

- **A1**: 16 new accounts, one IP, rapid exact-copy target-product burst.
- **A2**: 16 distributed new accounts, automated user agent, coordinated target
  and repeated split-local source sentences.
- **A3**: 16 aged accounts, slower negative-rating campaign and recycled texts.
- **A4**: one established account, rapid repeated-text review submissions.
- **N1**: 24 established genuine accounts behind shared campus NAT; varied texts.
- **N2**: 24 established genuine accounts enthusiastically reviewing a product
  launch; positive ratings and synchronized arrivals with varied texts.
- **G**: ordinary synthetic timing/network/account metadata around public text.

Each attack can have an initially unremarkable event; it remains labeled by its
generating scenario. The pipeline does not remove hard examples after evaluation.

## Schema and causal history

Dataset canonical keys:

```text
id, product_id, user_id, ip_hash, ip_prefix, user_agent, created_at,
account_created, rating, body, revision, scenario, true_label, split
```

Additional provenance fields: `source_group`, `source_row`, `source_sentiment`,
`template_group`, `metadata_origin`, and `text_origin`. `true_label=0` means
synthetic genuine behavior; `1` means synthetic attack. Dataset splits are
`train`, `validation`, and `test`.

Times accept finite Unix seconds or timezone-aware ISO-8601 strings. Ratings must
be finite numbers from 1 through 5. Revisions are positive integers. Account
creation cannot follow review creation; blank identifiers/text and text longer
than 20,000 characters are rejected. Serving does not require `scenario`,
`true_label`, `split`, or source annotations.

`FeatureExtractor.transform(rows, history=...)` returns rows **in input order**.
The history plus batch is contextual data, but only strictly earlier timestamps
contribute to an event. Equal-time/future events and the candidate's own ID are
excluded. History is a current snapshot with unique IDs; a candidate replaces
its old revision in that snapshot. Duplicate IDs within history or within a
query batch are rejected. This is not a full bitemporal revision-history engine.

### The ten features, in model input order

| Name | Exact definition |
|---|---|
| `reviews_per_ip_1h` | Earlier reviews from the same IP hash, age ≤ 3,600 seconds. |
| `reviews_per_ip_24h` | Earlier reviews from the same IP hash, age ≤ 86,400 seconds. |
| `accounts_per_ip_24h` | Distinct user IDs in that IP's preceding 24 hours. |
| `account_burst_10m` | Earlier reviews by the same user, age ≤ 600 seconds. |
| `product_burst_ratio` | `((product_count_30m + 1) / 0.5) / ((product_count_baseline + 47) / 23.5)`; the baseline is the preceding rolling 24 hours **excluding the recent 30 minutes**. |
| `rating_deviation` | Absolute difference from earlier same-product mean rating; genuine-training rating mean when no product history exists. |
| `text_max_similarity` | Maximum cosine TF-IDF similarity against **all strictly earlier reviews of the same product**, with no time cutoff; zero without same-product history. |
| `text_len_z` | Character length standardized using genuine-training mean/std (std floor 1). |
| `account_age_log` | `log1p(account_age_in_hours)`. |
| `ua_rarity` | Negative log of add-one-smoothed genuine-training UA probability, with one unknown-UA bucket. |

TF-IDF uses word uni/bigrams, at most 5,000 terms, fitted only on genuine training
texts. Text length, rating fallback, and UA statistics also fit only genuine
training. Prefix is retained in the canonical schema but is not a hidden 11th
feature. History contains previously observed attacks as well as genuine rows;
its labels are never used for feature computation.

F5's recent window is `0 < age_seconds <= 1800`; its disjoint baseline is
`1800 < age_seconds <= 86400`. Both rates are per hour. Smoothing contributes
one pseudo-review per half-hour bucket: `+1` for the recent half-hour and `+47`
for the preceding 23.5 hours. Empty history therefore gives ratio 1, and the
recent burst never contributes to its own denominator. This is a fixed prior,
not a quantity fitted using validation or test data.

## Models, inference, and calibration

1. Apply **`log1p` to F1–F5** (nonnegative counts and the rate ratio), leaving
   F6–F10 unchanged. Fit `StandardScaler` on those transformed 1,128 genuine
   training feature rows. The identical pure preprocessing function runs during
   inference; raw feature matrices and reason values remain unmodified.
2. Fit PCA on those standardized rows (four or six components), then a clipped
   min/max angle scaler to `[0, π]`, all exclusively on genuine training.
3. Fit Isolation Forest (150 trees) on **all ten** standardized features.
4. Select 24 genuine training rows by seeded sampling. Classical RBF OCSVM and
   quantum OCSVM receive the **same points and same angle-transformed PCA inputs**,
   with `nu=0.1`. Metadata exposes both training counts and selected IDs.
5. Quantum map: `ZZFeatureMap(reps=1, entanglement="linear")`.
   Explicit execution chain: **`qiskit_aer.primitives.Sampler` →
   `ComputeUncompute` → `FidelityQuantumKernel`**. Backend method `statevector`,
   `shots=None` means exact-probability local Aer simulation. It is not an implicit
   `StatevectorSampler`, a hardware run, or a finite-shot noise experiment.

The installed and tested stack is Qiskit **1.3.2**, Aer **0.16.1**, and
Qiskit Machine Learning **0.8.2**. These releases have an interface mismatch:
Aer Sampler inherits `BaseSamplerV1`, while QML's constructor checks its child
alias `BaseSampler`. A small multiple-inheritance compatibility subclass only
satisfies that type check; every primitive execution still uses actual Aer code.
Upstream deprecation warnings are expected with these pinned versions.

The model saves all 24 training angles and the 19 learned support vectors,
dual coefficients, and intercept. Inference computes
`K(new, support) @ dual_coef + intercept`, equivalent to the fitted OCSVM's
`K(new, train)` decision. It never evaluates `K(new, new)` as an inference kernel.
The Aer primitive is reconstructed on load instead of serializing runtime jobs.

Raw anomalies are negative decision functions. Each gets an empirical CDF
fitted once using **408 genuine validation** raw scores. Larger normalized scores
mean more anomalous; these are reference percentiles, **not fraud probabilities**.
Fixed reference arrays make scoring independent of request batch size, including
single-row requests. PCA projection uses deterministic row-wise contraction.

```text
classical mean = (IF + classical OCSVM) / 2
hybrid = (1 - quantum_weight) * classical mean + quantum_weight * quantum OCSVM
```

The quantum weight is selected **only on validation** from the fixed nonzero grid
`[0.1, 0.25, 0.5, 0.75]`. Each candidate has its own genuine-validation threshold
at ≤5% FPR; selection maximizes validation attack recall. Ties prefer 0.5, then
the weight closest to 0.5, then the lower weight. All candidates, thresholds,
recalls, and FPRs are saved under `metadata.fusion_selection`. Test data is never
used by this selector. For the current artifact:

| Quantum weight | Validation attack recall | Genuine validation FPR |
|---:|---:|---:|
| **0.10 (selected)** | **.640625** | .04902 |
| 0.25 | .546875 | .04902 |
| 0.50 | .062500 | .04902 |
| 0.75 | .031250 | .04902 |

The selected formula is `0.9 * classical mean + 0.1 * quantum OCSVM`.

Separate thresholds are calibrated using genuine validation rows only. Prediction
is **strictly `score > threshold`**. The order-statistic threshold permits at most
`floor(0.05 * genuine_validation_count)` positives, even with tied scores. The
observed validation FPR is 20/408 = 4.90% for each model. That is an empirical
validation constraint, not a guarantee for future populations. Frozen hybrid
suspicious threshold: **0.9156862745098039** for the seed-42 four-qubit artifact.

A separate frozen **watch** threshold uses the genuine-validation 80th-percentile
order statistic with the same conservative strict comparison. At most 20% of
genuine validation scores exceed it; the observed rate is 81/408 = 19.85%,
including suspicious scores. Hybrid watch threshold: **0.7627450980392158**.
Labels are `suspicious` above the suspicious threshold, `watch` above the watch
threshold otherwise, and `genuine` below or equal to the watch threshold. A tie
at the suspicious threshold is watch when it exceeds the watch threshold. If
both thresholds coincide, the watch band is empty. Precision/recall/F1 and FPR
in evaluation use the **suspicious** threshold; watch is not counted as a
positive fraud prediction.

## Serving and hardware-benchmark interfaces

```python
from pipeline.models import TrustRateModel

model = TrustRateModel.load("service/artifacts/model.joblib")
result = model.score_review(review=canonical_review, history=earlier_review_snapshot)
```

`score_review(review: dict, history: list[dict]) -> dict` returns:

```python
{
    "scores": {
        "isolation_forest": float,
        "classical_ocsvm": float,
        "quantum_ocsvm": float,
        "hybrid": float,
    },
    "label": "genuine" or "watch" or "suspicious",
    "reasons": [
        {"feature": str, "value": float, "code": str, "description": str,
         "training_z_magnitude": float},
        # three largest absolute deviations from genuine training statistics
    ],
    "backend": "aer_simulator",
    "model_version": str,
    "threshold": float,
    "watch_threshold": float,
    "comparison": ">",
}
```

Reason `value` is the **raw feature value**, before F1–F5 `log1p` and before
standard scaling. (F8/F9/F10 already have the z/log meanings given in their
feature definitions.) `training_z_magnitude` ranks deviations in the model's
preprocessed/standardized space. Reasons are descriptive deviations, not causal
attributions or proof of fraud. The human-readable `description` accompanies a
stable `code`, and the full map is persisted in `metadata.reason_code_map`:

| Code | Meaning |
|---|---|
| `IP_REVIEWS_1H` | Reviews from this IP in the preceding hour. |
| `IP_REVIEWS_24H` | Reviews from this IP in the preceding 24 hours. |
| `IP_ACCOUNTS_24H` | Distinct accounts using this IP in the preceding 24 hours. |
| `ACCOUNT_REVIEWS_10M` | Reviews by this account in the preceding 10 minutes. |
| `PRODUCT_RATE_RATIO` | Product's last-30-minute rate relative to its preceding 23.5-hour baseline. |
| `RATING_DEVIATION` | Absolute rating difference from the earlier product average. |
| `PRODUCT_TEXT_SIMILARITY` | Maximum similarity to strictly earlier reviews of this product. |
| `TEXT_LENGTH_Z` | Text length deviation from genuine training, in standard deviations. |
| `ACCOUNT_AGE_LOG_HOURS` | Natural log of one plus account age in hours. |
| `USER_AGENT_RARITY` | Negative log of this user agent's genuine-training frequency. |

`model.metadata` is a JSON-serializable dictionary containing the model
version, backend details, provenance, features, calibration, PCA variance,
training counts/IDs, reason map, watch thresholds, fusion selection, and
training/validation fingerprint. `model.quantum_train`
is a NumPy array of **already-scaled angles**, shape `(24, 4)` for the default
artifact, ready for a matching hardware-kernel benchmark without preprocessing
again. `model.quantum_support` contains support angles.

Training interface:
`TrustRateModel(qubits=4, n_train=24, seed=42).fit(canonical_rows, provenance=dict)`.
Rows include all three disjoint chronological splits for integrity validation;
test values are never passed to feature/model fitting or calibration.
`model.features.transform(rows, history)` gives the n-by-10 feature matrix;
`model.scores(X)` gives normalized score arrays in the same row order.

## Actual held-out results and limitations

Seed 42, four qubits, 24 quantum/classical OCSVM training points; 472 held-out
rows (408 genuine, 64 attacks). Version `trustrate-uci-v2-9eceba0ec859` includes
the requested PRD corrections and validation-only fusion selection; test results
do not choose parameters, source texts, metadata, or thresholds:

| Model | Precision | Recall | F1 | ROC AUC | PR AUC (average precision) | Test FPR |
|---|---:|---:|---:|---:|---:|---:|
| Isolation Forest | .6379 | .5781 | .6066 | .9297 | .6398 | .0515 |
| Classical OCSVM | .6182 | .5313 | .5714 | .8566 | .6823 | .0515 |
| Quantum OCSVM | .1389 | .0781 | .1000 | .6512 | .1844 | .0760 |
| Hybrid | .6230 | .5938 | .6080 | .8999 | .5692 | .0564 |

Hybrid detection: A1 16/16, A2 14/16, A3 0/16, A4 8/16. False positives:
baseline G 2/360, shared-NAT N1 17/24, launch N2 4/24. Single-class scenario
ROC/PR AUC values are `null`, not fabricated values.

The quantum model underperforms the classical baseline in this experiment;
**there is no demonstrated quantum advantage**. Aggregate FPR hides weaker
behavior on genuine shared-network/launch traps; N1 has a particularly high
70.83% false-positive rate. Hybrid test FPR is **5.64%**, exceeding the 5%
validation target: it is reported as measured rather than corrected by test-set
retuning. Real review text does not make
the synthetic fraud labels real. Reused source texts reduce effective sample
size; no independence-based confidence intervals are claimed. The implementation
is a reproducible methodological demo, not a validated production fraud detector.
Text similarity scans all supplied earlier same-product context; truncating that
history would change the feature definition. Large-scale serving would need
an indexed product-history similarity store and indexed temporal windows. Four/six-qubit
exact Aer is computationally small and cannot establish hardware scaling.

The ML test suite checks feature order/windows, same-time/future exclusion,
validation rejection, text/group leakage, genuine-only fit membership, explicit
Aer use, correct cross-kernel inference, tie-safe thresholds, batch invariance,
save/load/new-review inference, exact F5/F7/F9 semantics, train/infer log
preprocessing, raw reason values, watch boundaries, fusion-grid tie handling,
and evaluation with fit/calibration/fusion selection disabled. All **17 tests**
pass for the rebuilt artifact.
