"""
一键启动脚本：启动可视化流程与参数核对服务，并在默认浏览器中直接打开。
运行方式：
    .venv\\Scripts\\python run_web.py
"""

import threading
import time
import webbrowser
import uvicorn
from server.web_app import app, WEB_SERVER_HOST, WEB_SERVER_PORT


def open_browser():
    time.sleep(1.2)
    url = f"http://{WEB_SERVER_HOST}:{WEB_SERVER_PORT}/editor?session_id=session_debug&stage=1"
    print(f"\n[INFO] 已自动为您打开可视化编辑器: {url}\n")
    webbrowser.open(url)


if __name__ == "__main__":
    threading.Thread(target=open_browser, daemon=True).start()
    print(f"==================================================")
    print(f" 工业热工计算与选型测算系统 // 本地可视化服务启动")
    print(f" 服务地址: http://{WEB_SERVER_HOST}:{WEB_SERVER_PORT}")
    print(f" 按 Ctrl+C 可停止服务")
    print(f"==================================================")
    uvicorn.run(app, host=WEB_SERVER_HOST, port=WEB_SERVER_PORT, log_level="info")
