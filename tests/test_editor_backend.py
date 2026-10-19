"""真实进程与端口边界：清理编辑器监听，保留 MCP 连接和工程会话。"""

import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

ROOT = Path(__file__).resolve().parents[1]


def free_port(host="127.0.0.1"):
    with socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


def listening(port, host="127.0.0.1"):
    try:
        with socket.create_connection((host, port), timeout=0.2):
            return True
    except OSError:
        return False


async def wait_port(port, expected, host="127.0.0.1"):
    for _ in range(100):
        if listening(port, host) == expected:
            return
        await asyncio.sleep(0.05)
    assert listening(port, host) == expected, f"编辑器端口 {port} 未按要求{'释放' if not expected else '启动'}"


@asynccontextmanager
async def mcp_client(tmp_path, port):
    launcher = (
        "import sys;sys.path.insert(0,sys.argv[1]);from server import mcp_server as m;"
        "start=m.ensure_web_server_running;m.ensure_web_server_running=lambda:start(port=int(sys.argv[2]));"
        "m.webbrowser.open=lambda *a:False;m.run_server()"
    )
    parameters = StdioServerParameters(command=sys.executable, args=["-c", launcher, str(ROOT), str(port)],
        cwd=str(tmp_path), env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=30) as client:
            await client.initialize()
            yield client


async def call(client, name, **kwargs):
    response = await client.call_tool(name, kwargs)
    text = next(item.text for item in response.content if item.type == "text")
    try:
        return json.loads(text)
    except ValueError:
        return {"error": text}


def test_skill_cleanup_releases_port_without_exiting_mcp_or_losing_session(tmp_path):
    async def exercise():
        port = free_port()
        async with mcp_client(tmp_path, port) as client:
            proposed = await call(client, "match_or_propose_scenario", session_id="backend-lifecycle",
                                 user_requirements="自动化服务生命周期样例",
                                 scenario_id="scenario_electric_heater_salt_steam")
            assert proposed["status"] == "SCENARIO_PROPOSED", proposed
            await wait_port(port, True)
            with urlopen(f"http://127.0.0.1:{port}/api/session/backend-lifecycle", timeout=3) as response:
                before = json.load(response)
            cleanup = await call(client, "cleanup_editor_backend", port=port)
            await wait_port(port, False)
            assert cleanup["status"] == "READY", cleanup
            assert await call(client, "list_scenarios")
            assert (await call(client, "execute_calculation", session_id="backend-lifecycle"))["security_block"]
            assert (await call(client, "open_pipeline_editor", session_id="backend-lifecycle", stage=1))["status"] == "SUCCESS"
            await wait_port(port, True)
            with urlopen(f"http://127.0.0.1:{port}/api/session/backend-lifecycle", timeout=3) as response:
                assert json.load(response) == before
        await wait_port(port, False)
    asyncio.run(exercise())


def test_cleanup_can_stop_previous_mcp_web_listener_without_killing_its_connection(tmp_path):
    async def exercise():
        port = free_port()
        async with mcp_client(tmp_path, port) as previous:
            await call(previous, "match_or_propose_scenario", session_id="previous",
                       user_requirements="自动化服务生命周期样例", scenario_id="scenario_electric_heater_salt_steam")
            await wait_port(port, True)
            async with mcp_client(tmp_path, port) as current:
                result = await call(current, "cleanup_editor_backend", port=port)
                assert result == {"status": "READY", "port": port, "stopped": True}, result
                await wait_port(port, False)
                assert await call(previous, "list_scenarios")
                assert (await call(previous, "open_pipeline_editor", session_id="previous", stage=1))["status"] == "SUCCESS"
                await wait_port(port, True)
        await wait_port(port, False)
    asyncio.run(exercise())


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_cleanup_stops_owned_standalone_backend_and_can_repeat(tmp_path, host):
    connect_host = "::1" if host == "::1" else "127.0.0.1"
    try:
        port = free_port(connect_host)
    except OSError:
        pytest.skip("当前环境未启用所需回环地址")

    async def exercise():
        process = subprocess.Popen([sys.executable, str(ROOT / "run_web.py"), "--host", host, "--port", str(port), "--no-browser"],
            cwd=tmp_path, env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            await wait_port(port, True, connect_host)
            async with mcp_client(tmp_path, port) as client:
                result = await call(client, "cleanup_editor_backend", port=port)
                assert result == {"status": "READY", "port": port, "stopped": True}, result
                await wait_port(port, False, connect_host)
                stdout, stderr = process.communicate(timeout=5)
                assert process.returncode == 0, (stdout, stderr)
                assert await call(client, "cleanup_editor_backend", port=port) == {"status": "READY", "port": port, "stopped": False}
        finally:
            if process.poll() is None:
                process.terminate()
                process.communicate(timeout=5)
    asyncio.run(exercise())


def test_two_mcp_connections_can_alternate_cleanup_and_reopen_without_losing_ownership(tmp_path):
    async def exercise():
        port = free_port()
        async with mcp_client(tmp_path, port) as first:
            await call(first, "match_or_propose_scenario", session_id="first", user_requirements="自动化交错重开样例",
                       scenario_id="scenario_electric_heater_salt_steam")
            async with mcp_client(tmp_path, port) as second:
                assert (await call(second, "cleanup_editor_backend", port=port))["status"] == "READY"
                await call(second, "match_or_propose_scenario", session_id="second", user_requirements="自动化交错重开样例",
                           scenario_id="scenario_electric_heater_salt_steam")
                for _ in range(3):
                    assert (await call(first, "cleanup_editor_backend", port=port))["status"] == "READY"
                    assert (await call(first, "open_pipeline_editor", session_id="first", stage=1))["status"] == "SUCCESS"
                    assert (await call(second, "cleanup_editor_backend", port=port))["status"] == "READY"
                    assert (await call(second, "open_pipeline_editor", session_id="second", stage=1))["status"] == "SUCCESS"
                assert (await call(first, "cleanup_editor_backend", port=port))["status"] == "READY"
                await wait_port(port, False)
    asyncio.run(exercise())


def test_shutdown_endpoint_requires_instance_credential_and_same_origin(tmp_path):
    async def exercise():
        port = free_port()
        async with mcp_client(tmp_path, port) as client:
            await call(client, "match_or_propose_scenario", session_id="shutdown-boundary",
                       user_requirements="自动化服务生命周期样例", scenario_id="scenario_electric_heater_salt_steam")
            await wait_port(port, True)
            with urlopen(f"http://127.0.0.1:{port}/api/editor-backend", timeout=3) as response:
                identity = json.load(response)
            assert identity["service"] == "thermal-calc-sizing-editor"
            assert "token" not in identity
            for headers in ({}, {"X-Thermal-Editor-Token": "invalid"}, {"Origin": "https://unrelated.invalid"}):
                request = Request(f"http://127.0.0.1:{port}/api/editor-backend/shutdown", data=b"{}", headers=headers)
                with pytest.raises(HTTPError) as error:
                    urlopen(request, timeout=3)
                assert error.value.code == 403
                assert listening(port)
    asyncio.run(exercise())


def test_cleanup_preserves_unrelated_port_listener(tmp_path):
    class ForeignService(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"unrelated-service")

        def log_message(self, *args):
            pass

    foreign = ThreadingHTTPServer(("127.0.0.1", 0), ForeignService)
    port = foreign.server_port
    thread = threading.Thread(target=foreign.serve_forever, daemon=True)
    thread.start()
    try:
        async def exercise():
            async with mcp_client(tmp_path, port) as client:
                result = await call(client, "cleanup_editor_backend", port=port)
                assert "error" in result, result
                assert listening(port)
                with urlopen(f"http://127.0.0.1:{port}/", timeout=3) as response:
                    assert response.read() == b"unrelated-service"
                assert await call(client, "list_scenarios")
        asyncio.run(exercise())
    finally:
        foreign.shutdown()
        foreign.server_close()
        thread.join(timeout=3)
