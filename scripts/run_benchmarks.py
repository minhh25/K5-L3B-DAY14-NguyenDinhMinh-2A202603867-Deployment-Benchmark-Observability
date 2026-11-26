"""Run CP7 with real HTTP requests; retain failed SLOs rather than hiding them.

From repo root: .venv/bin/python scripts/run_benchmarks.py
"""
import json
import os
import platform
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
DEVELOP = ROOT / "06-lab-complete/benchmark-observability/develop"
REPORTS = ROOT / "reports"
RUNTIME = ROOT / ".runtime"
REPORTS.mkdir(exist_ok=True)
RUNTIME.mkdir(exist_ok=True)
RUNS = []


@contextmanager
def agent(version, port, **extra):
    env = {**os.environ, "AGENT_VERSION": version, "PORT": str(port),
           "MOCK_ERROR_RATE": "0.01", "MOCK_SLOW_RATE": "0.03", **extra}
    with (RUNTIME / f"benchmark-{port}.log").open("w") as log:
        process = subprocess.Popen([sys.executable, "app.py"], cwd=DEVELOP,
                                   env=env, stdout=log, stderr=log)
        try:
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError(f"Agent exited; see {log.name}")
                try:
                    with urlopen(f"http://127.0.0.1:{port}/health", timeout=1):
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("Agent startup timed out")
            yield f"http://127.0.0.1:{port}"
        finally:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def run(script, *args, expected=None):
    command = [sys.executable, script, *map(str, args)]
    print("Running:", " ".join(command[1:]), flush=True)
    result = subprocess.run(command, cwd=DEVELOP, capture_output=True, text=True)
    name = Path(args[args.index("--out") + 1]).stem
    (REPORTS / f"{name}.txt").write_text(result.stdout + result.stderr)
    # Keep the canonical reports at the required root and also at the CP7 path.
    canonical = REPORTS / f"{name}.json"
    canonical.write_bytes((DEVELOP / "reports" / f"{name}.json").read_bytes())
    RUNS.append({"command": command[1:], "exit_code": result.returncode,
                 "report": f"reports/{name}.json"})
    if result.returncode not in (0, 1) or (expected is not None and result.returncode != expected):
        raise RuntimeError(result.stdout + result.stderr)
    report = json.loads(canonical.read_text())
    print(json.dumps({k: report[k] for k in ("accuracy", "rps", "error_rate", "quality_gate", "slo")
                      if k in report}), flush=True)


def main():
    started = datetime.now(timezone.utc).isoformat()
    with agent("v1", 8001) as v1, agent("v2", 8002, MOCK_KB_PATCHES="0") as v2:
        run("eval/run_eval.py", "--url", v1, "--out", "reports/eval_v1.json", expected=1)
        run("eval/run_eval.py", "--url", v2, "--baseline", "reports/eval_v1.json",
            "--out", "reports/eval_v2.json", expected=0)
        for concurrency in (1, 10, 50, 100):
            run("load_test.py", "--url", v2, "--requests", 300, "--concurrency", concurrency,
                "--out", f"reports/load_v2_c{concurrency}.json")
    for slow in ("0", "0.03", "0.1"):
        with agent("v2", 8002, MOCK_KB_PATCHES="0", MOCK_SLOW_RATE=slow) as v2:
            run("load_test.py", "--url", v2, "--requests", 300, "--concurrency", 20,
                "--out", f"reports/load_v2_slow_{slow}.json")
    with agent("v2", 8002, MOCK_KB_PATCHES="1") as v2:
        run("eval/run_eval.py", "--url", v2, "--min-accuracy", 1.0,
            "--baseline", "reports/eval_v2.json", "--out", "reports/eval_v2_fixed.json", expected=0)
    # Deliberately regress to v1: CI must see a non-zero exit status.
    with agent("v1", 8001) as v1:
        run("eval/run_eval.py", "--url", v1, "--baseline", "reports/eval_v2_fixed.json",
            "--out", "reports/eval_regression.json", expected=1)
    (REPORTS / "benchmark-run.json").write_text(json.dumps({
        "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version, "platform": platform.platform(),
        "baseline_kb": "MOCK_KB_PATCHES=0", "fixed_kb": "MOCK_KB_PATCHES=1",
        "mock_error_rate": 0.01, "runs": RUNS,
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
