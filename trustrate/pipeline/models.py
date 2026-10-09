"""Classical and Qiskit quantum novelty models."""
from pathlib import Path
import joblib, numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.svm import OneClassSVM
from sklearn.preprocessing import StandardScaler

class TrustRateModel:
    def __init__(self, quantum=False, seed=42): self.quantum=quantum; self.seed=seed
    def fit(self,X):
        self.scaler=StandardScaler().fit(X); Z=self.scaler.transform(X); self.classical=IsolationForest(n_estimators=150,random_state=self.seed,contamination='auto').fit(Z); self.ocsvm=OneClassSVM(kernel='rbf',gamma='scale',nu=.12).fit(Z); self.backend='classical';
        if self.quantum:
            from .quantum import fit_quantum
            self.qkernel,self.qsvm=fit_quantum(Z, self.seed); self.backend='aer_simulator'
        return self
    def scores(self,X):
        Z=self.scaler.transform(X); a=-self.classical.decision_function(Z); a=(a-a.min())/(a.max()-a.min()+1e-9); c=-self.ocsvm.decision_function(Z); c=(c-c.min())/(c.max()-c.min()+1e-9)
        q=np.zeros(len(Z))
        if self.quantum: q=-self.qsvm.decision_function(self.qkernel.evaluate(Z, Z)); q=(q-q.min())/(q.max()-q.min()+1e-9)
        return {'isolation_forest':a,'classical_ocsvm':c,'quantum_ocsvm':q,'hybrid':.4*a+.3*c+.3*q if self.quantum else .55*a+.45*c}
    def save(self,path): Path(path).parent.mkdir(parents=True,exist_ok=True); joblib.dump(self,path)
    @classmethod
    def load(cls,path): return joblib.load(path)
