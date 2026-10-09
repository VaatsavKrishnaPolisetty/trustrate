"""FidelityQuantumKernel adapter; no IBM jobs are submitted here."""
import numpy as np
def fit_quantum(X,seed=42):
    from qiskit.circuit.library import ZZFeatureMap
    from qiskit_machine_learning.kernels import FidelityQuantumKernel
    from sklearn.svm import OneClassSVM
    fmap=ZZFeatureMap(feature_dimension=X.shape[1],reps=1,entanglement='linear')
    kernel=FidelityQuantumKernel(feature_map=fmap)
    K=kernel.evaluate(X)
    model=OneClassSVM(kernel='precomputed',nu=.12).fit(K)
    return kernel, model
