# Five-minute presentation

Open **http://127.0.0.1:8080/index.php**. Do not use the old static server on 4173.
Sign in with ADMIN_EMAIL/ADMIN_PASSWORD from local `db/.local/compose.env`;
do not project this credentials file. Nothing else needs to be installed now.

1. **Product (45 seconds).** Explain public UCI review text plus synthetic product/
   behavioral metadata. Raw and Genuine ratings are live database aggregates.
2. **Attack (60 seconds).** Moderation → choose a populated product → A1 → give
   an audit reason → inject. Forty reviews enter the real scoring queue. Refresh
   and filter flagged reviews; never promise every injected review is detected.
3. **Evidence (45 seconds).** Open a review: real classical/quantum/operational
   score bars, feature reasons, related IP/subnet/text/time leads. Restore or
   remove with an audit reason; refresh the product to show persistent changes.
4. **Qiskit (90 seconds).** Models → measured benchmark and circuit. Show
   `FidelityQuantumKernel`, genuine training, calibration, and the distinct guard.
   State that classical OCSVM is currently stronger; no quantum advantage claim.
   Show IBM receipt `db4ia6qmb58s73898ebg` on `ibm_marrakesh`: real 153-circuit
   kernel workload. It belongs to v2, not the active v3 model.
5. **Limits and reset (40 seconds).** Show v3's held-out NAT/launch traps (0/24
   false positives each) and low-and-slow failure (0/16 caught). Select the same
   product in demo reset, supply reason/confirmation, reset. Only button-injected
   rows are removed; public imports, ordinary reviews and audits remain.

Optional: Models → asynchronous experiment → enter a review ID → **Local noisy
Aer**. Poll the same receipt; this uses cached device noise and no new IBM quota.
IBM modes are optional and spend quota. Do not submit hardware merely to show
the existing verified result; avoid relying on queue time during the presentation.

**Network/API backup:** open `docs/backup.html`. This is an honest static evidence
snapshot, not a video or a claim of live offline hardware execution. Refresh it
after rebuilding with `.venv/bin/python -m pipeline.export_evidence`.

**If the app was closed:**
```bash
cd /Users/vaatsavkrishna/omnirush.ai/trustrate
php db/native.php start
.venv/bin/python -m service.local start
```
Skip native start if the dedicated database is already running. No reimport or
new IBM key is required. Inspect `.runtime/` logs locally if startup fails.
