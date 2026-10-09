"""Explicit IBM/noisy-Aer cross-kernels; errors never masquerade as hardware."""
from pathlib import Path
import os
import joblib
import numpy as np
from qiskit.circuit.library import ZZFeatureMap
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
from qiskit_machine_learning.kernels import FidelityQuantumKernel
from qiskit_machine_learning.state_fidelities import ComputeUncompute
from pipeline.quantum import support_decision

ROOT=Path(__file__).resolve().parents[2]
CACHE=ROOT/"service/artifacts/noise-backend.joblib"

def cache_noise(backend):
    from qiskit_aer.noise import NoiseModel
    record={"noise_model":NoiseModel.from_backend(backend),"backend":backend.name}
    CACHE.parent.mkdir(parents=True,exist_ok=True)
    joblib.dump(record,CACHE)
    return record

def noise_kernel(qubits):
    if not CACHE.exists():
        raise RuntimeError("No cached device noise model")
    from qiskit_aer.primitives import Sampler
    from qiskit.primitives import BaseSampler
    record=joblib.load(CACHE)
    class CompatibleAerSampler(Sampler,BaseSampler):
        pass
    sampler=CompatibleAerSampler(backend_options={"noise_model":record["noise_model"],"method":"density_matrix","max_parallel_threads":1},run_options={"shots":512,"seed":42},transpile_options={"seed_transpiler":42})
    kernel=FidelityQuantumKernel(feature_map=ZZFeatureMap(qubits,reps=1,entanglement="linear"),fidelity=ComputeUncompute(sampler),max_circuits_per_job=128)
    return kernel,"aer_noise_"+record["backend"]

def hardware_kernel(qubits,progress):
    from dotenv import dotenv_values
    from qiskit_ibm_runtime import QiskitRuntimeService,SamplerV2
    config=dotenv_values(ROOT/".env")
    token=os.environ.get("IBM_QUANTUM_TOKEN") or config.get("IBM_QUANTUM_TOKEN")
    if not token: raise RuntimeError("IBM credentials not configured")
    service=QiskitRuntimeService(channel="ibm_cloud",token=token,instance=os.environ.get("IBM_INSTANCE") or config.get("IBM_INSTANCE") or None)
    name=os.environ.get("IBM_BACKEND_NAME") or config.get("IBM_BACKEND_NAME")
    backend=service.backend(name) if name else service.least_busy(operational=True,simulator=False,min_num_qubits=qubits)
    try: cache_noise(backend)
    except OSError: pass  # Read-only artifact mounts must not prevent real hardware execution.
    timeout=int(os.environ.get("IBM_TIMEOUT_SEC","90"))
    class TimedJob:
        def __init__(self,job): self.job=job
        def result(self):
            try: return self.job.result(timeout=timeout)
            except Exception:
                # Do not silently leave an unlimited queue/run behind on fallback.
                try: self.job.cancel(); progress({"cancel_requested":True})
                except Exception: progress({"cancel_requested":False})
                raise
        def __getattr__(self,name): return getattr(self.job,name)
    class RecordingSampler(SamplerV2):
        def run(self,pubs,*,shots=None):
            progress({"submission_attempted":True})
            job=super().run(pubs,shots=256)
            progress({"ibm_job_id":job.job_id(),"backend":backend.name})
            return TimedJob(job)
    sampler=RecordingSampler(mode=backend)
    fidelity=ComputeUncompute(sampler,pass_manager=generate_preset_pass_manager(backend=backend,optimization_level=1,seed_transpiler=42))
    return FidelityQuantumKernel(feature_map=ZZFeatureMap(qubits,reps=1,entanglement="linear"),fidelity=fidelity,max_circuits_per_job=128),backend.name

def quantum_raw(model,X,mode,progress=lambda update:None):
    _,angles=model._angles(X)
    info={"ibm_job_id":None,"fallback_reason":None}
    def report(update): info.update(update); progress(update)
    if mode=="aer_noise":
        kernel,backend=noise_kernel(model.qubits)
    else:
        try:
            kernel,backend=hardware_kernel(model.qubits,report)
            values=-support_decision(kernel,angles,model.quantum_support,model.quantum_dual,model.quantum_intercept)
            return values,{**info,"backend":backend}
        except Exception as exc:
            if mode!="ibm_with_fallback": raise
            info["fallback_reason"]=type(exc).__name__
            # Only one attempt. Any job receipt stays attached to the fallback.
            try: kernel,backend=noise_kernel(model.qubits)
            except Exception:
                from pipeline.quantum import make_kernel
                kernel,backend=make_kernel(model.qubits),"aer_simulator"
                info["fallback_reason"]+="; device noise unavailable, ideal Aer used"
    values=-support_decision(kernel,angles,model.quantum_support,model.quantum_dual,model.quantum_intercept)
    if not np.isfinite(values).all(): raise ValueError("Nonfinite quantum score")
    return values,{**info,"backend":backend}
