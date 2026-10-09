# TrustRate: real application walkthrough

1. Open http://127.0.0.1:8080/index.php. Use a populated dataset product.
   Explain that public UCI review text is real, but products and cyber metadata
   are synthetic. Raw/Genuine values come from MySQL, not fixed UI constants.
2. Sign in using `ADMIN_EMAIL` / `ADMIN_PASSWORD` from the local-only
   `db/.local/compose.env` file. Do not project this credentials file on screen.
3. Open Moderation. Filter `flagged`; open an evidence link. Show actual
   classical/quantum/hybrid bars and feature reason values.
4. Remove or restore a review with an audit reason. Refresh the product page;
   ratings reflect the persistent status. Review the audit trail.
5. In Synthetic attack laboratory, select A1 and a populated product. Injection
   inserts 12 synthetic reviews into MySQL with pending status. The real PHP
   worker calls FastAPI/Aer, saves scores and flags only model-selected rows.
   **Do not promise every attack is detected.** Refresh the queue to inspect.
6. Submit your own review. Edit it; the old score is invalidated and revision
   increments. The worker rescoring uses the same trained model as seeded rows.
7. Open Models. Show the measured held-out table, ROC/PR curves, NAT failure
   rate, feature map and `FidelityQuantumKernel` configuration.
8. Show the completed actual IBM kernel experiment:
   - Backend `ibm_marrakesh`
   - Job `db4ia6qmb58s73898ebg`
   - 153 fidelity circuits / 256 shots / four qubits
   - 12 genuine training points and six stratified demonstration points
   - Recorded hardware-vs-Aer kernel MAE, approximately 0.014715
9. State the limitations: quantum underperforms classical here; hybrid test FPR
   exceeds the validation target, shared-NAT false positives remain unacceptable,
   and low-and-slow detection is weak. This is a real functioning research
   pipeline, not a production-ready fraud detector or quantum-advantage result.

No new hardware submission is required for the walkthrough. Saved genuine
hardware results remain visible if IBM is temporarily unreachable. This is
cached evidence, not a new offline hardware execution.

There is no reset-to-baseline button or backup video yet. Repeated attacks add
new persistent reviews and audit records; use moderation rather than pretending
they disappear at application restart.
