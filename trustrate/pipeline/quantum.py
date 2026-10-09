"""Explicit, exact-probability local Aer fidelity kernel; never IBM hardware."""
import numpy as np
from sklearn.svm import OneClassSVM


def make_kernel(qubits=4, seed=42):
    if qubits not in (4, 6):
        raise ValueError("qubits must be 4 or 6")
    from qiskit.circuit.library import ZZFeatureMap
    from qiskit_aer.primitives import Sampler
    from qiskit.primitives import BaseSampler
    from qiskit_machine_learning.state_fidelities import ComputeUncompute
    from qiskit_machine_learning.kernels import FidelityQuantumKernel

    # shots=None requests exact probabilities from Aer, rather than a seeded
    # finite-shot estimator whose noise could depend on request batching.
    # QML 0.8.2 checks the deprecated BaseSampler alias, but Aer 0.16.1
    # inherits its parent BaseSamplerV1. This compatibility subclass changes
    # only isinstance compatibility: all execution is the real Aer Sampler.
    class CompatibleAerSampler(Sampler, BaseSampler):
        pass

    sampler = CompatibleAerSampler(
        backend_options={"method": "statevector", "max_parallel_threads": 1},
        transpile_options={"seed_transpiler": seed},
        run_options={"shots": None, "seed": seed},
    )
    fidelity = ComputeUncompute(sampler=sampler)
    feature_map = ZZFeatureMap(feature_dimension=qubits, reps=1, entanglement="linear")
    return FidelityQuantumKernel(feature_map=feature_map, fidelity=fidelity,
                                 enforce_psd=True, evaluate_duplicates="all",
                                 max_circuits_per_job=256)


def fit_quantum(angles, seed=42):
    angles = np.asarray(angles, dtype=float)
    kernel = make_kernel(angles.shape[1], seed)
    gram = kernel.evaluate(angles)
    svm = OneClassSVM(kernel="precomputed", nu=.1).fit(gram)
    return kernel, svm


def support_decision(kernel, angles, support_angles, dual_coef, intercept, batch_size=64):
    """Equivalent to OCSVM K(new,train) decision, using only support columns."""
    angles = np.asarray(angles, dtype=float)
    decisions = []
    for start in range(0, len(angles), batch_size):
        cross = kernel.evaluate(angles[start:start + batch_size], support_angles)
        # Fixed row-wise reduction avoids batch-size-dependent BLAS paths and
        # spurious floating-point status warnings on macOS Accelerate.
        decisions.extend(np.einsum("ij,j->i", cross, np.asarray(dual_coef).ravel(), optimize=False) + float(intercept))
    return np.asarray(decisions)
