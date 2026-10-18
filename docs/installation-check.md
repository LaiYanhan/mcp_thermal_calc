# Skill 与 MCP 完成度及安装检查

检查日期：2026-10-18（Asia/Shanghai）。

结论：当前项目已具备可安装使用的 Skill 与本机 stdio MCP 业务闭环。本次补齐了依赖清单、真实 MCP 协议回归和 Codex 安装说明，并修正 Skill 与当前实现不一致之处。

## 已执行的验证

- `uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt`：声明的依赖已安装。
- `uv pip check --python .venv/Scripts/python.exe`：环境依赖兼容。
- `.venv/Scripts/python.exe -m pytest -q`：阶段控制修订后 91 项通过，包含前端 Node.js 回归；Node.js 单独执行 23 项通过。
- `tests/test_mcp_stdio.py`：真实子进程初始化、工具发现、场景目录、公式目录、未授权计算拦截，以及测试样例确认后的完整计算均通过。使用隔离数据目录，不打开浏览器。
- Skill Creator `quick_validate.py`：项目 Skill 与安装副本均通过。
- 读取实际用户 MCP 配置启动服务：握手成功，发现 11 个工具、2 个场景、25 个公式；目录查询成功。

## 本机安装结果

- 用户 MCP 配置：`C:/Users/ASUS/.codex/config.toml`。
- 新服务名：`thermal-calc-sizing`；启用 stdio，使用项目 `.venv/Scripts/python.exe` 运行 `server/mcp_server.py` 的绝对路径。
- 设置 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8` 和指向项目 `.data` 的 `THERMAL_CALC_DATA_DIR`。
- Skill：`C:/Users/ASUS/.codex/skills/thermal-calculation-agent/SKILL.md`，与项目修订版内容一致。
- 配置修改前已在同目录保存 `config.toml.thermal-install-*.bak`；已有服务与配置值保留。
- 安装后的后续轮次可发现 Skill；MCP 尚未刷新时重启 Codex 后新建聊天。

## 范围与后续维护

上述证据支持本机业务工作流可用，不代表全部工业热工场景均已建模或完成实际设备性能认证。热泵管道采用用户给定 COP，未建模热源侧、温升和设备性能曲线。工程测算仍需要对所选场景与参数分别确认。

本次协议测试和已有回归验证了编辑器相关代码路径，但未重新进行完整人工浏览器交互验收。

后续按用户确认的流程修订：Skill 恢复原状态机图、工程红线、六步流程、报告清单和 Python 公式模板，场景扩展沿用 Python 源码及注册表。阶段切换由 AI 显式调用 `open_pipeline_editor` 控制，前端控制仅在 `run_web.py --debug` 时启用；微调参数不即时重算。

MCP 运行依赖当前项目目录；移动项目后需重新注册。修改项目 Skill 后需同步用户目录副本。动态公式、管道和会话仍保存于 `.data`；本次测试未覆盖或重置现有工程数据。
