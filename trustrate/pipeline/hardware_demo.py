"""Submit a tiny, real IBM Quantum smoke run when credentials are configured."""
import os
import socket
from qiskit import QuantumCircuit
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2

token=os.getenv("IBM_QUANTUM_TOKEN")
if not token: raise SystemExit("Set IBM_QUANTUM_TOKEN in trustrate/.env first")
try:
    socket.gethostbyname("auth.quantum.ibm.com")
except socket.gaierror as exc:
    raise SystemExit("IBM Quantum is unreachable because DNS cannot resolve auth.quantum.ibm.com. Check Wi-Fi/VPN/DNS, then retry; no IBM job was submitted.") from exc
try:
    service=QiskitRuntimeService(channel="ibm_quantum", token=token, instance=os.getenv("IBM_INSTANCE") or None)
except Exception as exc:
    raise SystemExit(f"IBM Quantum authentication/setup failed before job submission: {type(exc).__name__}. Check network, token, and account access; no IBM job was submitted.") from exc
backend=service.backend(os.getenv("IBM_BACKEND_NAME")) if os.getenv("IBM_BACKEND_NAME") else service.least_busy(simulator=False, operational=True, min_num_qubits=6)
qc=QuantumCircuit(1); qc.h(0); qc.measure_all()
job=SamplerV2(mode=backend).run([qc], shots=128)
print({"backend":backend.name,"job_id":job.job_id(),"status":str(job.status())})
