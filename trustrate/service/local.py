"""Start/stop only TrustRate-owned local processes; no system services changed."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / ".runtime"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "stop", "status"])
    action = parser.parse_args().action
    RUN.mkdir(exist_ok=True, mode=0o700)
    state_path = RUN / "processes.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if action == "status":
        print(json.dumps(state, indent=2)); return
    if action == "stop":
        for name, pid in state.items():
            # Check command line to avoid killing an unrelated reused PID.
            cmd = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True).stdout
            if str(ROOT) in cmd or (name == "api" and "service.app.main:app" in cmd):
                os.killpg(pid, signal.SIGTERM)
        state_path.unlink(missing_ok=True)
        print("Stopped owned web/API/worker processes; database data retained."); return
    if state:
        raise SystemExit("Local process state exists. Use status or stop before starting again.")
    config = ROOT / "db/.local/compose.env"
    if not config.exists():
        raise SystemExit("Run php db/native.php start and php db/run.php init first")
    env = {**os.environ, **{k: v for k, v in dotenv_values(config).items() if v is not None},
           "SCORING_URL": "http://127.0.0.1:8001", "WEB_LISTEN": "127.0.0.1:8080", "DEMO_MODE": "1"}
    commands = {
        "api": [sys.executable, "-m", "uvicorn", "service.app.main:app", "--host", "127.0.0.1", "--port", "8001", "--no-access-log"],
        "web": ["php", str(ROOT / "db/run.php"), "serve"],
        "worker": ["php", str(ROOT / "db/run.php"), "score-worker"],
    }
    for name, command in commands.items():
        with (RUN / f"{name}.log").open("ab") as log:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=log, start_new_session=True)
        state[name] = process.pid
        state_path.write_text(json.dumps(state))
        if name == "api":
            for _ in range(30):
                try:
                    with urllib.request.urlopen("http://127.0.0.1:8001/health", timeout=2) as r:
                        if json.load(r)["status"] == "ready": break
                except Exception:
                    time.sleep(1)
            else: raise SystemExit("API not ready. Inspect .runtime/api.log; stop before retrying.")
    print("TrustRate PHP: http://127.0.0.1:8080/index.php")
    print("Scoring health: http://127.0.0.1:8001/health")
    print("Worker is scoring queued MySQL reviews. Logs are in .runtime/.")

if __name__ == "__main__":
    main()
