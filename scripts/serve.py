"""One command, whole stack: database, API, worker, console — then connect.

    python scripts/serve.py

Brings up everything a demo or reviewer needs, in dependency order, and opens
the browser already pointed at the right backend:

  1. Postgres   starts the ``sentry-postgres`` container (launching Docker
                Desktop first if the daemon is asleep), waits for readiness,
                and applies migrations to an empty database (never a populated
                one — that is what ``db_init.py --recreate`` is for).
  2. API        binds the first free port among 8000/8077/8081/8001/8090.
                Port 8000 is the single most contended port in desktop Docker,
                so a hard-coded default is how "BACKEND: OFFLINE" happens.
  3. Worker     ``python -m worker.main`` (claims queued jobs).
  4. Console    static server on 8080 (falls back to 8081/8082), then the
                system browser opens on
                ``http://127.0.0.1:<console>/index.html?backend=http://127.0.0.1:<api>``
                — the ``?backend`` parameter plus the console's own port scan
                and one-click dev session mean the page is connected with zero
                manual steps.

Every child process is terminated on Ctrl+C. Nothing is written outside this
repository except through the project's own code paths.

Exit codes: 0 normal shutdown, 1 something failed to start (the reason is
printed, with the exact command to fix it where one exists).
"""

from __future__ import annotations

import argparse
import atexit
import os
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.request import urlopen

REPO = Path(__file__).resolve().parents[1]
API_PORT_CANDIDATES = [8000, 8077, 8081, 8001, 8090]
CONSOLE_PORT_CANDIDATES = [8080, 8081, 8082]
HEALTH_TIMEOUT_S = 60.0
PG_READY_TIMEOUT_S = 60.0
DOCKER_START_TIMEOUT_S = 120.0


def log(msg: str) -> None:
    print(f"[serve] {msg}", flush=True)


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) != 0


def pick_port(candidates: list[int], what: str) -> int:
    for port in candidates:
        if port_free(port):
            return port
    raise SystemExit(
        f"[serve] no free port for the {what} among {candidates}; "
        f"free one and retry, or pass --{'api' if what == 'API' else 'console'}-port")


def docker_daemon_up() -> bool:
    return subprocess.run(
        ["docker", "info"], capture_output=True, timeout=20).returncode == 0


def ensure_postgres(start_docker: bool) -> None:
    """Daemon up, container up, accepting connections — or explain what to do."""
    try:
        if not docker_daemon_up():
            if not start_docker:
                raise SystemExit("[serve] Docker daemon is down; start Docker Desktop first")
            desktop = Path(r"C:\Program Files\Docker\Docker\Docker Desktop.exe")
            if not desktop.exists():
                raise SystemExit(f"[serve] Docker daemon is down and {desktop} was not found")
            log("Docker daemon asleep; starting Docker Desktop …")
            subprocess.Popen([str(desktop)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            deadline = time.monotonic() + DOCKER_START_TIMEOUT_S
            while time.monotonic() < deadline:
                if docker_daemon_up():
                    break
                time.sleep(3)
            else:
                raise SystemExit("[serve] Docker daemon did not come up within "
                                 f"{DOCKER_START_TIMEOUT_S:.0f}s")
        status = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", "sentry-postgres"],
            capture_output=True, text=True, timeout=20)
        if status.returncode != 0 or status.stdout.strip() != "true":
            log("starting container sentry-postgres …")
            subprocess.run(["docker", "start", "sentry-postgres"],
                           check=True, capture_output=True, timeout=60)
        deadline = time.monotonic() + PG_READY_TIMEOUT_S
        while time.monotonic() < deadline:
            ready = subprocess.run(
                ["docker", "exec", "sentry-postgres", "pg_isready", "-U", "postgres"],
                capture_output=True, timeout=15)
            if ready.returncode == 0:
                log("Postgres is accepting connections on 127.0.0.1:54322")
                return
            time.sleep(2)
        raise SystemExit("[serve] Postgres container did not become ready; "
                         "see: docker logs --tail 50 sentry-postgres")
    except FileNotFoundError:
        raise SystemExit("[serve] docker CLI not found on PATH; "
                         "install Docker Desktop or start Postgres manually")


def apply_migrations_if_empty() -> None:
    """Apply migrations to an *empty* database; never touch a populated one."""
    probe = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "db_init.py"), "--verify"],
        cwd=REPO, capture_output=True, text=True, timeout=120)
    out = probe.stdout + probe.stderr
    if probe.returncode == 0 and "core tables present" in out:
        log("database schema verified")
        return
    if "core tables present" in out:
        log("WARNING: database schema failed verification (not auto-fixing):")
        print(out, flush=True)
        log("inspect with: python scripts/db_init.py --verify")
        return
    log("empty database detected; applying migrations …")
    init = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "db_init.py")],
        cwd=REPO, capture_output=True, text=True, timeout=300)
    if init.returncode != 0:
        print(init.stdout + init.stderr, flush=True)
        raise SystemExit("[serve] migration failed; fix and re-run serve.py")
    log("migrations applied")


def wait_healthy(url: str, timeout_s: float) -> dict:
    deadline = time.monotonic() + timeout_s
    last = None
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=3) as resp:
                import json
                body = json.loads(resp.read().decode())
                if body.get("status") == "ok":
                    return body
                last = f"health answered but not ok: {body}"
        except Exception as exc:  # noqa: BLE001 - not up yet, or broken
            last = str(exc)
        time.sleep(1.5)
    raise SystemExit(f"[serve] {url} not healthy within {timeout_s:.0f}s ({last})")


def spawn(cmd: list[str], name: str, logfile: Path):
    handle = logfile.open("ab")
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    # Smooth single-machine demo defaults (explicit env still wins):
    # DEV_AUTH for one-click demo sessions, local artifact store so a
    # DB-backed demo without object storage just works.
    env.setdefault("DEV_AUTH", "true")
    env.setdefault("ARTIFACT_STORE", "local")
    proc = subprocess.Popen(cmd, cwd=REPO, stdout=handle, stderr=handle, env=env)
    log(f"{name} started (pid {proc.pid}, log: {logfile})")
    return proc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api-port", type=int, default=None,
                        help="fixed API port (default: first free of 8000/8077/…)")
    parser.add_argument("--console-port", type=int, default=None,
                        help="fixed console port (default: first free of 8080/…)")
    parser.add_argument("--no-worker", action="store_true",
                        help="do not start the job worker. Use this before "
                             "running the GPU test suite: the worker loads the "
                             "1.1 GB checkpoint onto the card and keeps it, and "
                             "on an 8 GiB laptop GPU the suite then OOMs even "
                             "though nvidia-smi reports free VRAM (WDDM backs "
                             "CUDA allocations with host commit, which is what "
                             "actually runs out).")
    parser.add_argument("--no-browser", action="store_true",
                        help="do not open the system browser")
    parser.add_argument("--no-docker-start", action="store_true",
                        help="never launch Docker Desktop ourselves")
    args = parser.parse_args()

    children: list[subprocess.Popen] = []
    logs = REPO / "serve-logs"
    logs.mkdir(exist_ok=True)

    def shutdown(*_a) -> None:
        for proc in children:
            if proc.poll() is None:
                proc.terminate()
        deadline = time.monotonic() + 8
        for proc in children:
            while proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.2)
            if proc.poll() is None:
                proc.kill()
        # proc.stdout is None (redirected to log files); nothing to close here.
        # Log file handles are owned by Popen and closed on process exit.

    atexit.register(shutdown)
    signal.signal(signal.SIGINT, lambda *a: (_ for _ in ()).throw(KeyboardInterrupt))

    ensure_postgres(start_docker=not args.no_docker_start)
    apply_migrations_if_empty()

    api_port = args.api_port or pick_port(API_PORT_CANDIDATES, "API")
    console_port = args.console_port or pick_port(CONSOLE_PORT_CANDIDATES, "console")

    api = spawn([sys.executable, "-m", "uvicorn", "backend.main:app",
                 "--host", "127.0.0.1", "--port", str(api_port)],
                "API", logs / "api.log")
    children.append(api)
    health = wait_healthy(f"http://127.0.0.1:{api_port}/v1/health", HEALTH_TIMEOUT_S)
    db_state = "db ok" if health.get("db") else "db DOWN (console will say so)"
    log(f"API healthy on http://127.0.0.1:{api_port} ({db_state}, "
        f"dev_auth={str(health.get('dev_auth')).lower()})")

    worker = None

    if args.no_worker:
        log("worker skipped (--no-worker); jobs submitted from the console will "
            "stay QUEUED until a worker is started: python -m worker.main")
    else:
        worker = spawn([sys.executable, "-m", "worker.main"], "worker", logs / "worker.log")
        children.append(worker)

    static = spawn([sys.executable, "-m", "http.server", str(console_port),
                    "--bind", "127.0.0.1"], "console", logs / "console.log")
    children.append(static)
    time.sleep(1.5)
    if static.poll() is not None:
        raise SystemExit("[serve] console static server exited immediately; "
                         f"see {logs / 'console.log'}")

    if console_port not in (8080,):
        log(f"WARNING: console is on :{console_port}; if the page cannot reach "
            "the API, add http://127.0.0.1:" + str(console_port) +
            " to CORS_ORIGINS in .env and restart.")

    url = (f"http://127.0.0.1:{console_port}/index.html"
           f"?backend=http%3A%2F%2F127.0.0.1%3A{api_port}")
    log("stack is up:")
    print(f"""
  console   http://127.0.0.1:{console_port}/index.html
  API       http://127.0.0.1:{api_port}/v1/health   (docs at /docs)
  Postgres  127.0.0.1:54322  (container: sentry-postgres)
  logs      {logs}
""", flush=True)
    if not args.no_browser:
        try:
            webbrowser.open(url)
            log("browser opened on the console (already pointed at the API)")
        except Exception:  # noqa: BLE001 - headless machines are fine
            log(f"open this URL manually: {url}")

    try:
        while True:
            time.sleep(5)
            for name, proc in (("API", api), ("console", static)):
                if proc.poll() is not None:
                    log(f"{name} exited (code {proc.returncode}); shutting the stack down")
                    return 1
            if worker is not None and worker.poll() is not None:
                log(f"worker exited (code {worker.returncode}); continuing without it")
                worker = None
    except KeyboardInterrupt:
        log("Ctrl+C: stopping API, worker and console (Postgres stays up)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
