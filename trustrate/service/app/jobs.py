"""Bounded persisted job receipts. Restart never resubmits an uncertain IBM job."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import json
from pathlib import Path
from threading import Lock
import uuid

DIRECTORY=Path(__file__).resolve().parents[2]/".runtime/jobs"
POOL=ThreadPoolExecutor(max_workers=1,thread_name_prefix="quantum-job")
LOCK=Lock()

def write(job):
    DIRECTORY.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=DIRECTORY/(job["job_id"]+".json")
    temp=path.with_suffix(".tmp")
    temp.write_text(json.dumps(job,allow_nan=False)); temp.replace(path)

def recover():
    DIRECTORY.mkdir(parents=True,exist_ok=True,mode=0o700)
    for path in DIRECTORY.glob("job_*.json"):
        job=json.loads(path.read_text())
        if job["status"] in ("queued","running"):
            job.update(status="interrupted",error="Server restarted. Inspect any IBM receipt; no automatic resubmission.")
            write(job)

def get(job_id):
    if not job_id.startswith("job_") or len(job_id)!=36 or any(c not in "0123456789abcdef" for c in job_id[4:]):
        raise KeyError(job_id)
    path=DIRECTORY/(job_id+".json")
    if not path.exists(): raise KeyError(job_id)
    return json.loads(path.read_text())

def submit(ids,mode,predict):
    with LOCK:
        # No unbounded queue or quota-burning automatic retries.
        if any(json.loads(p.read_text())["status"] in ("queued","running") for p in DIRECTORY.glob("job_*.json")):
            raise RuntimeError("A hardware batch is already queued/running")
        job={"job_id":"job_"+uuid.uuid4().hex,"status":"queued","review_ids":ids,"mode":mode,"submitted_at":datetime.now(timezone.utc).isoformat(),"ibm_job_id":None}
        write(job)
        def run():
            def progress(update): job.update(update); write(job)
            try:
                progress({"status":"running"})
                results=predict(ids,mode=mode,progress=progress)
                progress({"status":"fell_back" if any(r.get("fallback_reason") for r in results) else "completed","results":results,"backend":results[0]["backend"]})
            except Exception as exc:
                progress({"status":"failed","error":type(exc).__name__,"message":"No automatic retry; inspect stored IBM receipt before submitting again."})
        POOL.submit(run)
        return {k:job[k] for k in ("job_id","status","submitted_at")}
