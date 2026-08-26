import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_http(url: str, timeout: float = 30.0, headers: dict = None) -> tuple[int, str]:
    headers = headers or {}
    start = time.time()
    last_err = None
    while time.time() - start < timeout:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                body = resp.read().decode("utf-8")
                return resp.status, body
        except urllib.error.HTTPError as ex:
            body = ex.read().decode("utf-8")
            return ex.code, body
        except Exception as ex:
            last_err = ex
            time.sleep(0.3)
    raise TimeoutError(f"Timed out waiting for {url}: {last_err}")


def port_is_closed(port: int, host: str = "127.0.0.1", timeout: float = 5.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            res = s.connect_ex((host, port))
            if res != 0:
                return True
        time.sleep(0.2)
    return False


def run_smoke():
    print("=== STARTING REAL OFFLINE RUNTIME SMOKE ===")
    tmp_home = Path(tempfile.mkdtemp(prefix="hermes_smoke_home_"))
    api_key = f"smoke_key_{secrets.token_hex(16)}"
    owner_id = "local-owner"

    gw_port = find_free_port()
    app_port = find_free_port()
    web_port = find_free_port()

    while len({gw_port, app_port, web_port}) < 3:
        app_port = find_free_port()
        web_port = find_free_port()

    print(f"Temporary HERMES_HOME: {tmp_home}")
    print(f"Allocated ports -> Gateway: {gw_port}, App API: {app_port}, Web: {web_port}")

    config_path = tmp_home / "runtime.yaml"
    config_path.write_text(
        f"""runtime:
  mode: development
  provider_mode: fake
  gateway_port: {gw_port}
  app_api_port: {app_port}
  web_port: {web_port}
  enable_web: true
  enable_telegram: false
  enable_workers: false
  enable_mcp: false
""",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["HERMES_HOME"] = str(tmp_home)
    env["HERMES_API_KEY"] = api_key
    env["HERMES_OWNER_ID"] = owner_id
    env["PYTHONUNBUFFERED"] = "1"

    cmd = [
        sys.executable,
        "-m",
        "hermes_cli.main",
        "start",
        "--config",
        str(config_path),
        "--no-open-browser",
    ]

    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0

    print(f"Phase 1: Starting supervisor process: {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        env=env,
        cwd=str(Path.cwd()),
        creationflags=creationflags,
    )

    try:
        # Step 2: Gateway readiness
        print("Checking Gateway readiness...")
        code, body = wait_for_http(f"http://127.0.0.1:{gw_port}/health/ready", timeout=20.0)
        print(f"Gateway health/ready returned HTTP {code}: {body.strip()}")
        assert code == 200, f"Expected 200, got {code}"

        # Step 3: App API readiness
        print("Checking App API readiness...")
        code, body = wait_for_http(f"http://127.0.0.1:{app_port}/health/ready", timeout=20.0)
        print(f"App API health/ready returned HTTP {code}: {body.strip()}")
        assert code == 200, f"Expected 200, got {code}"

        # Step 4: Web UI binding
        print("Checking Web UI dev server binding...")
        code, body = wait_for_http(f"http://127.0.0.1:{web_port}", timeout=25.0)
        print(f"Web UI returned HTTP {code}")
        assert code == 200, f"Expected 200, got {code}"

        # Step 5: App API bootstrap HTML and extract session token
        print("Requesting App API bootstrap HTML...")
        code, html = wait_for_http(f"http://127.0.0.1:{app_port}/", timeout=5.0)
        assert code == 200
        assert api_key not in html, "SECURITY VIOLATION: HERMES_API_KEY found in bootstrap HTML"
        assert "window.__HERMES_SESSION_TOKEN__" in html
        assert "hermes_session=" in html

        import re
        m = re.search(r'window\.__HERMES_SESSION_TOKEN__="([^"]+)"', html)
        assert m, "Failed to extract session token from bootstrap HTML"
        browser_session_token = m.group(1)
        print(f"Obtained browser session token: {browser_session_token[:8]}...")

        auth_headers = {
            "Authorization": f"Bearer {browser_session_token}",
            "Content-Type": "application/json",
        }

        # Step 6: POST /api/omni/turn through App API
        print("Submitting Turn 1 via POST /api/omni/turn on App API...")
        turn1_req = urllib.request.Request(
            f"http://127.0.0.1:{app_port}/api/omni/turn",
            data=json.dumps({"conversation_id": "smoke-omni-1", "message": "Turn 1 question"}).encode("utf-8"),
            headers={**auth_headers, "Idempotency-Key": "smoke-omni-turn-1"},
            method="POST",
        )
        with urllib.request.urlopen(turn1_req, timeout=10.0) as turn1_resp:
            turn1_lines = turn1_resp.read().decode("utf-8").strip().splitlines()
            turn1_events = [json.loads(line) for line in turn1_lines]

        print(f"Turn 1 received {len(turn1_events)} events: {[e['event_type'] for e in turn1_events]}")
        assert [e["event_type"] for e in turn1_events] == ["text_delta", "completed"]

        # Step 7: Replay events after Turn 1
        print("Querying event replay after Turn 1...")
        replay_req = urllib.request.Request(
            f"http://127.0.0.1:{app_port}/api/events/replay?owner_id={owner_id}",
            headers=auth_headers,
        )
        with urllib.request.urlopen(replay_req, timeout=5.0) as replay_resp:
            replay_data = json.loads(replay_resp.read().decode("utf-8"))

        print(f"Replay data count: {replay_data['count']}, cursors: {[e['cursor'] for e in replay_data['events']]}")
        assert replay_data["count"] == 2
        assert [e["cursor"] for e in replay_data["events"]] == [1, 2]

        # Step 8: Turn 2 in same session
        print("Submitting Turn 2 via POST /api/omni/turn on App API...")
        turn2_req = urllib.request.Request(
            f"http://127.0.0.1:{app_port}/api/omni/turn",
            data=json.dumps({"conversation_id": "smoke-omni-1", "message": "Turn 2 question"}).encode("utf-8"),
            headers={**auth_headers, "Idempotency-Key": "smoke-omni-turn-2"},
            method="POST",
        )
        with urllib.request.urlopen(turn2_req, timeout=10.0) as turn2_resp:
            turn2_lines = turn2_resp.read().decode("utf-8").strip().splitlines()
            turn2_events = [json.loads(line) for line in turn2_lines]

        print(f"Turn 2 received {len(turn2_events)} events: {[e['event_type'] for e in turn2_events]}")
        assert [e["event_type"] for e in turn2_events] == ["text_delta", "completed"]

        with urllib.request.urlopen(replay_req, timeout=5.0) as replay_resp:
            replay_data = json.loads(replay_resp.read().decode("utf-8"))
        print(f"Replay after Turn 2: count={replay_data['count']}, cursors={[e['cursor'] for e in replay_data['events']]}")
        assert replay_data["count"] == 4
        assert [e["cursor"] for e in replay_data["events"]] == [1, 2, 3, 4]

        # Step 9: Graceful shutdown of Phase 1
        print("Stopping supervisor process tree for graceful shutdown...")
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        else:
            proc.terminate()
        try:
            proc.wait(timeout=10.0)
            print("Supervisor terminated successfully.")
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5.0)

        assert port_is_closed(gw_port), f"Gateway port {gw_port} still open after shutdown!"
        assert port_is_closed(app_port), f"App API port {app_port} still open after shutdown!"
        assert port_is_closed(web_port), f"Web UI port {web_port} still open after shutdown!"
        print("Verified all ports are cleanly closed.")

    finally:
        if proc.poll() is None:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
            else:
                proc.kill()
            proc.wait()

    # Step 10: Phase 2 - Restart supervisor with the exact same database
    print("\nPhase 2: Restarting supervisor on same database to verify persistence...")
    proc2 = subprocess.Popen(
        cmd,
        env=env,
        cwd=str(Path.cwd()),
        creationflags=creationflags,
    )

    try:
        print("Waiting for restarted Gateway and App API readiness...")
        code, _ = wait_for_http(f"http://127.0.0.1:{gw_port}/health/ready", timeout=20.0)
        assert code == 200
        code, _ = wait_for_http(f"http://127.0.0.1:{app_port}/health/ready", timeout=20.0)
        assert code == 200

        # Extract new browser session token for restarted App API process
        code, html2 = wait_for_http(f"http://127.0.0.1:{app_port}/", timeout=5.0)
        m2 = re.search(r'window\.__HERMES_SESSION_TOKEN__="([^"]+)"', html2)
        assert m2
        browser_session_token2 = m2.group(1)
        auth_headers2 = {
            "Authorization": f"Bearer {browser_session_token2}",
            "Content-Type": "application/json",
        }

        # Step 11: Replay after restart must return all 4 previous events
        print("Checking replay after restart...")
        replay_req2 = urllib.request.Request(
            f"http://127.0.0.1:{app_port}/api/events/replay?owner_id={owner_id}",
            headers=auth_headers2,
        )
        with urllib.request.urlopen(replay_req2, timeout=5.0) as replay_resp:
            replay_data = json.loads(replay_resp.read().decode("utf-8"))

        print(f"Replay after restart: count={replay_data['count']}, cursors={[e['cursor'] for e in replay_data['events']]}")
        assert replay_data["count"] == 4
        assert [e["cursor"] for e in replay_data["events"]] == [1, 2, 3, 4]

        # Step 12: Turn 3 in same session
        print("Submitting Turn 3 via POST /api/omni/turn...")
        turn3_req = urllib.request.Request(
            f"http://127.0.0.1:{app_port}/api/omni/turn",
            data=json.dumps({"conversation_id": "smoke-omni-1", "message": "Turn 3 question"}).encode("utf-8"),
            headers={**auth_headers2, "Idempotency-Key": "smoke-omni-turn-3"},
            method="POST",
        )
        with urllib.request.urlopen(turn3_req, timeout=10.0) as turn3_resp:
            turn3_lines = turn3_resp.read().decode("utf-8").strip().splitlines()
            turn3_events = [json.loads(line) for line in turn3_lines]

        assert [e["event_type"] for e in turn3_events] == ["text_delta", "completed"]

        with urllib.request.urlopen(replay_req2, timeout=5.0) as replay_resp:
            replay_data = json.loads(replay_resp.read().decode("utf-8"))

        print(f"Replay after Turn 3: count={replay_data['count']}, cursors={[e['cursor'] for e in replay_data['events']]}")
        assert replay_data["count"] == 6
        assert [e["cursor"] for e in replay_data["events"]] == [1, 2, 3, 4, 5, 6]

        # Security check: Forged owner_id rejected
        print("Testing forged owner rejection...")
        forged_req = urllib.request.Request(
            f"http://127.0.0.1:{app_port}/api/omni/turn",
            data=json.dumps({"conversation_id": "smoke-omni-1", "message": "Forged", "owner_id": "forged-owner"}).encode("utf-8"),
            headers=auth_headers2,
            method="POST",
        )
        try:
            with urllib.request.urlopen(forged_req, timeout=5.0) as resp:
                raise AssertionError("Expected 403 Forbidden for forged owner")
        except urllib.error.HTTPError as ex:
            print(f"Forged owner correctly rejected with HTTP {ex.code}")
            assert ex.code == 403

        # Graceful shutdown of Phase 2
        print("Shutting down supervisor Phase 2...")
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc2.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        else:
            proc2.terminate()
        try:
            proc2.wait(timeout=10.0)
            print("Phase 2 supervisor terminated successfully.")
        except subprocess.TimeoutExpired:
            proc2.kill()
            proc2.wait(timeout=5.0)

        assert port_is_closed(gw_port)
        assert port_is_closed(app_port)
        assert port_is_closed(web_port)
        print("Verified all ports cleanly closed after Phase 2.")

    finally:
        if proc2.poll() is None:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc2.pid)], capture_output=True)
            else:
                proc2.kill()
            proc2.wait()

    print("\n=== REAL OFFLINE RUNTIME SMOKE PASSED ALL 12 CRITERIA ===")


if __name__ == "__main__":
    run_smoke()
