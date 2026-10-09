"""Explicit, resumable IBM fidelity-kernel experiment, never a fake receipt.

submit creates ONE hardware job; collect only retrieves that job. Retrying
collect never consumes another submission. Secrets are loaded locally and
neither exceptions from the SDK nor credentials are printed.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if not __package__:
    sys.path.insert(0, str(ROOT))

import numpy as np
from dotenv import dotenv_values
from qiskit import transpile
from qiskit.circuit.library import ZZFeatureMap
from qiskit_machine_learning.state_fidelities import ComputeUncompute
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
from sklearn.svm import OneClassSVM

from pipeline.data import load_reviews
from pipeline.models import TrustRateModel
from pipeline.quantum import make_kernel

ARTIFACTS = ROOT / "service/artifacts"
RECEIPT = ARTIFACTS / "hardware.json"
PLAN = ARTIFACTS / "hardware-plan.json"

def save(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2))
    temp.replace(path)

def runtime():
    config = dotenv_values(ROOT / ".env")
    token = os.environ.get("IBM_QUANTUM_TOKEN") or config.get("IBM_QUANTUM_TOKEN")
    instance = os.environ.get("IBM_INSTANCE") or config.get("IBM_INSTANCE") or None
    if not token:
        raise SystemExit("Set IBM_QUANTUM_TOKEN locally in .env; never paste it into chat.")
    # Pinned Runtime 0.36.1 uses ibm_cloud for the current platform. Do not
    # restore the retired ibm_quantum channel / auth.quantum.ibm.com endpoint.
    return QiskitRuntimeService(channel="ibm_cloud", token=token, instance=instance)

def submit(args):
    if RECEIPT.exists() and json.loads(RECEIPT.read_text()).get("status") != "NOT_SUBMITTED_VERIFIED":
        raise SystemExit("An experiment receipt already exists. Run collect; no job was submitted again.")
    model = TrustRateModel.load(ARTIFACTS / "model.joblib")
    rows = load_reviews(ROOT / "data/reviews.jsonl")
    test = [r for r in rows if r["split"] == "test"]
    # Selection depends on scenario labels solely to demonstrate both classes;
    # this tiny stratified subset is NOT a fair full-test hardware benchmark.
    selected = [next(r for r in test if r["scenario"] == s) for s in ("G", "N1", "A1", "A2", "A3", "A4")]
    X = model.features.transform(selected, history=rows)
    _, test_angles = model._angles(X)
    training = model.quantum_train[:args.n_train]
    angles = np.concatenate([training, test_angles])
    pairs = [(i, j) for i in range(len(angles)) for j in range(i+1, len(angles))]
    fmap = ZZFeatureMap(feature_dimension=model.qubits, reps=1, entanglement="linear")
    # Use QML's actual compute-uncompute circuit constructor, not an unrelated
    # single-qubit demonstration. P(00...0) is the pairwise fidelity kernel.
    builder = make_kernel(model.qubits).fidelity
    circuits = []
    for i, j in pairs:
        a = fmap.assign_parameters(angles[i])
        b = fmap.assign_parameters(angles[j])
        circuits.append(builder.create_fidelity_circuit(a, b))
    service = runtime()
    config = dotenv_values(ROOT / ".env")
    name = os.environ.get("IBM_BACKEND_NAME") or config.get("IBM_BACKEND_NAME")
    backend = service.backend(name) if name else service.least_busy(simulator=False, operational=True, min_num_qubits=model.qubits)
    isa = transpile(circuits, backend=backend, optimization_level=1, seed_transpiler=42)
    plan = {"model_version": model.model_version, "angles": angles.tolist(), "pairs": pairs,
            "n_train": len(training), "test_review_ids": [r["id"] for r in selected],
            "test_scenarios": [r["scenario"] for r in selected],
            "test_labels": [r["true_label"] for r in selected],
            "shots": args.shots, "qubits": model.qubits}
    save(PLAN, plan)
    # Record intent BEFORE submit. An ambiguous submit must be resolved from
    # IBM workloads, never automatically repeated and charged again.
    evidence = {"status": "submitting", "backend": backend.name, "ibm_job_id": None,
                "experiment": "ZZFeatureMap fidelity-kernel OCSVM", "model_version": model.model_version,
                "qubits": model.qubits, "reps": 1, "n_train": len(training), "n_test": len(selected),
                "shots": args.shots, "circuits": len(circuits),
                "max_transpiled_depth": max(c.depth() for c in isa),
                "submitted_at": datetime.now(timezone.utc).isoformat(),
                "plan_sha256": hashlib.sha256(PLAN.read_bytes()).hexdigest(),
                "limitation": "Small stratified hardware experiment; not the full held-out benchmark and not a quantum advantage claim."}
    save(RECEIPT, evidence)
    job = SamplerV2(mode=backend).run(isa, shots=args.shots)
    evidence.update(ibm_job_id=job.job_id(), status="SUBMITTED")
    save(RECEIPT, evidence)
    print(json.dumps({k:evidence[k] for k in ("ibm_job_id", "backend", "status", "circuits", "shots")}))

def collect():
    if not RECEIPT.exists():
        raise SystemExit("No hardware receipt. Use submit once.")
    receipt = json.loads(RECEIPT.read_text())
    if not receipt.get("ibm_job_id"):
        raise SystemExit("Submission outcome is uncertain. Inspect IBM workloads; do not resubmit automatically.")
    job = runtime().job(receipt["ibm_job_id"])
    status = str(job.status())
    if status != "DONE":
        receipt["status"] = status; save(RECEIPT, receipt)
        print(json.dumps({"ibm_job_id": job.job_id(), "status": status})); return
    plan = json.loads(PLAN.read_text())
    result = job.result()
    gram = np.eye(len(plan["angles"]))
    for (i,j), pub in zip(plan["pairs"], result):
        counts = pub.data.meas.get_counts()
        fidelity = counts.get("0" * plan["qubits"], 0) / sum(counts.values())
        gram[i,j] = gram[j,i] = fidelity
    if len(result) != len(plan["pairs"]) or not np.isfinite(gram).all():
        raise ValueError("Incomplete or invalid hardware kernel results")
    n = plan["n_train"]
    train = gram[:n,:n]
    # Hardware shot noise can make a kernel indefinite; PSD projection is
    # applied to training only, matching FidelityQuantumKernel's intent.
    eigenvalues, eigenvectors = np.linalg.eigh(train)
    psd = np.einsum("ik,k,jk->ij", eigenvectors, np.maximum(eigenvalues, 0), eigenvectors, optimize=False)
    if not np.isfinite(psd).all():
        raise ValueError("Invalid PSD training matrix")
    model = OneClassSVM(kernel="precomputed", nu=.1).fit(psd)
    hardware_raw = -model.decision_function(gram[n:,:n])
    aer = make_kernel(plan["qubits"]).evaluate(np.asarray(plan["angles"]))
    aer_model = OneClassSVM(kernel="precomputed", nu=.1).fit(aer[:n,:n])
    aer_raw = -aer_model.decision_function(aer[n:,:n])
    np.save(ARTIFACTS / "hardware-kernel.npy", gram)
    np.save(ARTIFACTS / "hardware-aer-kernel.npy", aer)
    # Render the actual feature map, rather than the former hand-written sketch.
    circuit = ZZFeatureMap(feature_dimension=plan["qubits"], reps=1, entanglement="linear")
    (ARTIFACTS / "circuit.txt").write_text(str(circuit.decompose().draw(output="text")))
    receipt.update(status="DONE", result_verified=True, completed_at=datetime.now(timezone.utc).isoformat(),
                   kernel_mean_absolute_difference=float(np.mean(np.abs(gram-aer))),
                   minimum_train_eigenvalue=float(eigenvalues.min()), psd_projection="training only",
                   results=[{"review_id":rid,"scenario":sc,"synthetic_label":lab,
                             "hardware_anomaly_raw":float(h),"aer_anomaly_raw":float(a)}
                            for rid,sc,lab,h,a in zip(plan["test_review_ids"],plan["test_scenarios"],plan["test_labels"],hardware_raw,aer_raw)])
    save(RECEIPT, receipt)
    print(json.dumps({"ibm_job_id":job.job_id(),"status":"DONE","kernel_verified":True,
                      "circuits":receipt["circuits"],"kernel_mae":receipt["kernel_mean_absolute_difference"]}))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("action", choices=["submit","collect"])
    parser.add_argument("--n-train",type=int,choices=range(4,25),default=12)
    parser.add_argument("--shots",type=int,choices=[128,256,512,1024],default=256)
    args=parser.parse_args()
    try:
        submit(args) if args.action=="submit" else collect()
    except SystemExit:
        raise
    except Exception as exc:
        # SDK errors may contain request details. Do not echo them with secrets.
        print(f"Hardware step failed ({type(exc).__name__}). Inspect receipt status before retrying; no automatic resubmission.", file=sys.stderr)
        raise SystemExit(1) from None

if __name__=="__main__":
    main()
