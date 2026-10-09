"""Export a static offline evidence page, not a fabricated live demo/video."""
import html
import json
from pathlib import Path

def main():
    root=Path(__file__).resolve().parents[1]
    metrics=json.loads((root/"service/artifacts/metrics.json").read_text())
    hardware=json.loads((root/"service/artifacts/hardware.json").read_text())
    esc=lambda value:html.escape(str(value))
    table="".join("<tr><th>"+esc(name)+"</th>"+"".join("<td>"+esc(round(row.get(key) or 0,4))+"</td>" for key in ("precision","recall","f1","false_positive_rate"))+"</tr>" for name,row in metrics["models"].items())
    scenarios="".join(f"<tr><th>{esc(name)}</th><td>{esc(row['count'])}</td><td>{esc(row['confusion']['tp'])}</td><td>{esc(row['confusion']['fp'])}</td><td>{esc(row['confusion']['fn'])}</td></tr>" for name,row in metrics['scenarios'].items())
    page=f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TrustRate · Offline evidence</title>
<style>body{{font:16px system-ui;background:#f8f8f3;color:#17221f;max-width:1050px;margin:auto;padding:35px}}h1{{font-size:48px}}section{{background:white;border:1px solid #dce3dd;border-radius:16px;padding:26px;margin:24px 0;overflow:auto}}table{{border-collapse:collapse;width:100%}}th,td{{padding:12px;text-align:left;border-bottom:1px solid #dce3dd}}code{{overflow-wrap:anywhere}}.notice{{border-left:4px solid #236b4b;padding:16px;background:#e6f2ea}}@media(max-width:600px){{body{{padding:16px}}h1{{font-size:32px}}}}</style>
<h1>TrustRate ✦</h1><p class="notice">Offline evidence snapshot. Not a running website, not a video, and not a new hardware execution.</p>
<section><h2>Architecture</h2><p>PHP/MySQL → read-only FastAPI → genuine-trained classical models + real Qiskit Aer fidelity kernel → model ranking and explicit two-signal operational guard → persisted moderation queue.</p><p>Actual public UCI Amazon sentences with synthetic behavior metadata. Fraud labels are simulated; sentiment is not fraud.</p></section>
<section><h2>Measured held-out results</h2><p>Model <code>{esc(metrics['metadata']['model_version'])}</code>. v3 dataset, frozen validation decisions. Corrected scenario methodology differs from v2.</p><table><tr><th>Component</th><th>Precision</th><th>Recall</th><th>F1</th><th>FPR</th></tr>{table}</table><p>The guard, not quantum superiority, drives current alert eligibility. Full-feature classical OCSVM outperforms the guarded hybrid; quantum contributes to ranking but shows no demonstrated detection benefit.</p></section>
<section><h2>Scenario audit</h2><table><tr><th>Scenario</th><th>Count</th><th>Detected attacks</th><th>False positives</th><th>Missed attacks</th></tr>{scenarios}</table></section>
<section><h2>Verified IBM kernel experiment</h2><p>Status: {esc(hardware['status'])}; backend: <strong>{esc(hardware['backend'])}</strong></p><p>Job: <code>{esc(hardware['ibm_job_id'])}</code></p><p>{hardware['circuits']} fidelity circuits, {hardware['shots']} shots, {hardware['qubits']} qubits. Kernel MAE vs Aer: {hardware['kernel_mean_absolute_difference']:.6f}.</p><p>Experiment model: <code>{esc(hardware['model_version'])}</code>. This is the retained v2 hardware result, not v3 hardware evidence. Its small stratified sample is not the full test benchmark.</p></section>
<section><h2>Data attribution and limits</h2><p>{esc(metrics['metadata']['provenance']['citation'])}. CC BY 4.0. <a href="https://archive.ics.uci.edu/dataset/331/sentiment+labelled+sentences">Official dataset</a>.</p><p>Low-and-slow attacks remain missed. No quantum advantage, production fraud accuracy, or zero real-world false-positive guarantee is claimed.</p></section></html>"""
    path=root/"docs/backup.html"
    path.write_text(page)
    print("Exported docs/backup.html from real saved results (no credentials or review bodies)")

if __name__=="__main__": main()
