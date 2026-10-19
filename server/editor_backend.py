"""编辑器监听的启动、退出及同项目旧监听清理；不终止 MCP 宿主。"""

from hashlib import sha256
from http.client import HTTPConnection, HTTPException
from ipaddress import ip_address
import json
import os
from pathlib import Path
import secrets
import socket
import threading
import time
from typing import Any

import uvicorn

from core.storage import data_directory, read_json, record_path, write_json

WEB_SERVER_HOST = "127.0.0.1"
WEB_SERVER_PORT = 8765
SERVICE = "thermal-calc-sizing-editor"
PROJECT_ID = sha256(os.path.normcase(str(Path(__file__).resolve().parents[1])).encode()).hexdigest()


def editor_base_url(host, port):
    return f"http://[{host}]:{port}" if ":" in host else f"http://{host}:{port}"


def bind_address(host, port):
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    family, _, _, _, address = next((item for item in addresses if item[0] == socket.AF_INET), addresses[0])
    return family, address


def listening(host, port):
    try:
        with socket.create_connection((host, port), timeout=0.2):
            return True
    except OSError:
        return False


class EditorBackend:
    def __init__(self):
        self._lock = threading.RLock()
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._socket: socket.socket | None = None
        self._owner: dict[str, Any] | None = None
        self._owner_path: Path | None = None

    def public_identity(self):
        with self._lock:
            if self._owner is None:
                return None
            return {key: value for key, value in self._owner.items() if key != "token"}

    def request_shutdown(self, token):
        with self._lock:
            if self._owner is None or not secrets.compare_digest(token.encode("utf-8"), self._owner["token"].encode("ascii")):
                return False
            assert self._server is not None
            self._server.should_exit = True
            return True

    def _create(self, app, host, port) -> uvicorn.Server:
        family, address = bind_address(host, port)
        sock = socket.socket(family)
        try:
            if os.name == "nt":
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if family == socket.AF_INET6:
                sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            sock.bind(address)
            sock.listen(128)
            owner = {"service": SERVICE, "project_id": PROJECT_ID, "instance_id": secrets.token_hex(16),
                     "pid": os.getpid(), "host": address[0], "port": port, "token": secrets.token_urlsafe(32)}
            # 路径含实例 ID；旧实例只会删除自己的文件，跨进程重开不会复用该路径。
            path = record_path("editor-backends", f"{port}:{owner['instance_id']}")
            write_json(path, owner)
        except OSError as error:
            sock.close()
            raise RuntimeError(f"无法启动编辑器端口 {port}；请先调用 cleanup_editor_backend 检查并清理本工具旧监听") from error
        self._server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))
        self._socket, self._owner, self._owner_path = sock, owner, path
        return self._server

    def _run(self):
        with self._lock:
            server, sock, owner, path = self._server, self._socket, self._owner, self._owner_path
            assert server is not None and sock is not None and owner is not None and path is not None
        try:
            server.run(sockets=[sock])
        finally:
            with self._lock:
                sock.close()
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    # 归属文件异常不能阻止监听和本进程资源释放。
                    pass
                finally:
                    self._server = self._thread = self._socket = self._owner = self._owner_path = None

    def start(self, app, host=WEB_SERVER_HOST, port=WEB_SERVER_PORT):
        with self._lock:
            stopping = self._server is not None and self._server.should_exit
        if stopping:
            self.stop()
        with self._lock:
            if self._server is not None:
                assert self._owner is not None
                if (bind_address(host, port)[1][0], port) != (self._owner["host"], self._owner["port"]):
                    raise RuntimeError("当前进程的编辑器已监听另一地址，请先清理原监听")
                server, thread = self._server, self._thread
            else:
                server = self._create(app, host, port)
                thread = threading.Thread(target=self._run, daemon=True)
                self._thread = thread
                thread.start()
        assert server is not None and thread is not None
        deadline = time.monotonic() + 5
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        if not server.started or not thread.is_alive():
            self.stop()
            raise RuntimeError("编辑器后端未能完成启动")
        return editor_base_url(host, port)

    def serve(self, app, host=WEB_SERVER_HOST, port=WEB_SERVER_PORT):
        """独立 run_web 入口也登记归属，接受同一清理协议。"""
        with self._lock:
            if self._server is not None:
                raise RuntimeError("当前进程已有编辑器监听")
            self._create(app, host, port)
            self._thread = threading.current_thread()
        self._run()

    def stop(self, port=None):
        with self._lock:
            if self._server is None:
                return False
            assert self._owner is not None and self._thread is not None
            if port is not None and port != self._owner["port"]:
                return False
            self._server.should_exit = True
            thread = self._thread
        if thread is not threading.current_thread():
            thread.join(timeout=5)
            if thread.is_alive():
                raise RuntimeError("编辑器后端仍在退出中，请稍后重试清理")
        return True


editor_backend = EditorBackend()


def _shutdown_peer(host, port, owners):
    """文件和监听者的实例标识必须同时匹配，才发送实例退出凭证。"""
    try:
        # 直连本机监听，不使用环境代理或跟随 HTTP 重定向。
        connection = HTTPConnection(host, port, timeout=2)
        try:
            connection.request("GET", "/api/editor-backend")
            response = connection.getresponse()
            if response.status != 200:
                raise ValueError("监听者未提供有效身份")
            identity = json.load(response)
            owner = next((item for item in owners if identity == {key: value for key, value in item.items() if key != "token"}), None)
            if owner is None:
                raise ValueError("监听身份与本项目记录不一致")
            connection.request("POST", "/api/editor-backend/shutdown", body=b"{}",
                               headers={"X-Thermal-Editor-Token": owner["token"], "Content-Type": "application/json"})
            response = connection.getresponse()
            if response.status != 202:
                raise ValueError("监听者未接受退出请求")
            response.read()
        finally:
            connection.close()
        return True
    except (OSError, HTTPException, ValueError, KeyError):
        return False


def cleanup_editor_listener(port=WEB_SERVER_PORT):
    stopped = editor_backend.stop(port)
    hosts = {"127.0.0.1", "::1"}
    requested = set()
    owners_by_host: dict[str, list[dict[str, Any]]] = {}
    for path in (data_directory() / "editor-backends").glob("*.json"):
        try:
            owner = read_json(path)
            if (not isinstance(owner, dict) or owner.get("service") != SERVICE or owner.get("project_id") != PROJECT_ID
                    or owner.get("port") != port or not isinstance(owner.get("token"), str)):
                continue
            host = {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(owner["host"], owner["host"])
            if not isinstance(host, str) or not ip_address(host).is_loopback:
                continue
        except (OSError, ValueError, KeyError, TypeError):
            continue
        hosts.add(host)
        owners_by_host.setdefault(host, []).append(owner)
    for host, owners in owners_by_host.items():
        if listening(host, port) and _shutdown_peer(host, port, owners):
            requested.add(host)
            stopped = True
    unknown = {host for host in hosts if host not in requested and listening(host, port)}
    if unknown:
        raise RuntimeError(f"端口 {port} 已占用，无法确认或关闭本项目旧编辑器；保留占用进程，请检查独立服务或重启旧版 MCP")
    deadline = time.monotonic() + 5
    while any(listening(host, port) for host in requested):
        if time.monotonic() >= deadline:
            raise RuntimeError(f"编辑器端口 {port} 尚未释放，请稍后重试")
        time.sleep(0.05)
    return {"status": "READY", "port": port, "stopped": stopped}
