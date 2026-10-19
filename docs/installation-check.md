# Skill、JSON 资产与 MCP 安装检查

本文用于检查项目依赖、Skill、JSON 资产和 MCP 的安装方式。首次安装命令见 [README](../README.md)，业务流程见 [项目 Skill](../skills/thermal-calculation-agent/SKILL.md)，架构依据见 [ADR-0014](adr/0014-pure-json-declarative-formulas-and-pipelines.md)。

## 依赖与服务检查

在项目根目录执行：

```powershell
uv pip check --python .venv/Scripts/python.exe
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe run_web.py --list
```

- 依赖兼容性检查应通过；完整测试包含 Node.js 前端行为回归和真实 MCP stdio 子进程测试。
- 默认资产目录应能发现 2 个场景、25 个原子公式；添加自定义 JSON 后，以实际目录结果为准。
- `tests/test_mcp_stdio.py` 验证 11 个 MCP 工具、JSON 注册、目录发现、未授权计算拦截及确认后的完整计算，测试使用隔离资产和数据目录。
- MCP 应使用项目虚拟环境的 Python 启动 `server/mcp_server.py`；通过当前项目位置生成启动路径，使用 `PYTHONUTF8=1` 和 `PYTHONIOENCODING=utf-8` 处理中文协议。

## Skill 与工具接口检查

项目 Skill 源为 `skills/thermal-calculation-agent/`，包含 `SKILL.md` 及 `references/json-definitions.md`。安装位置从 `CODEX_HOME` 或当前用户目录解析，避免在配置示例中写入真实机器路径。

同步主文档和参考文件后，检查链接完整、文件内容一致。保留原 Skill 的工程红线、状态机图、六步详细流程、确认话术、参数表格、报告清单和注意事项；架构调整只修改相关技术部分。

更新后需重启旧 MCP 进程。若客户端工具缓存未刷新，再重启客户端并新建聊天。检查注册工具参数为 `formula_definition`、`pipeline_definition`，停用旧 `formula_code`、`pipeline_code` 和 `sub_category`。注册成功不授予计算权限；场景及参数仍须分别确认。

## 已安装 Skill 的同步

在项目根目录执行以下 PowerShell 示例。各目录从环境变量和当前项目位置解析；同步前备份，保留安装目录中的其他资源：

```powershell
$projectRoot = (Get-Location).Path
$codexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
$skillSource = Join-Path $projectRoot 'skills\thermal-calculation-agent'
$skillTarget = Join-Path $codexRoot 'skills\thermal-calculation-agent'
$backupTarget = Join-Path $codexRoot ('backups\thermal-calculation-agent\' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
if (Test-Path -LiteralPath $skillTarget) {
    New-Item -ItemType Directory -Path (Split-Path $backupTarget) -Force | Out-Null
    Copy-Item -LiteralPath $skillTarget -Destination $backupTarget -Recurse
}
New-Item -ItemType Directory -Path $skillTarget -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $skillSource 'SKILL.md') -Destination (Join-Path $skillTarget 'SKILL.md') -Force
New-Item -ItemType Directory -Path (Join-Path $skillTarget 'references') -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $skillSource 'references\json-definitions.md') -Destination (Join-Path $skillTarget 'references\json-definitions.md') -Force
```

## 资产、会话与编辑器

公式和已注册管道位于项目 `formulas/`、`pipelines/`；`THERMAL_CALC_ASSET_DIR` 可指定包含这两个目录的资产根目录。启动时先发现公式，再发现管道；重复 ID 或无效定义会阻止加载。MCP 注册校验后原子写入 JSON 并即时注册，手工修改文件后需重启。

会话草稿、参数与布局位于数据目录的 `sessions/` 下，默认使用项目 `.data/sessions/`；可通过 `THERMAL_CALC_DATA_DIR` 调整。重启后需要重新确认。历史 `.data/operators.json`、`.data/pipelines/` 不再自动加载，需要的定义另行审核转为标准 JSON。数据目录设置不会改变资产目录。

编辑器阶段由 Agent 调用 `open_pipeline_editor` 控制；前端控制仅在 `run_web.py --debug` 时启用，参数修改不即时重算。MCP 编辑器默认使用 8765 端口；独立 Web 同时运行时指定其他 `--port`。

热泵基准使用给定 COP，未建模热源侧或设备性能曲线。应用层不拦截范围、熔盐温区及水汽相态；工程判断仍由使用者完成。测试通过不代表所有工业场景或设备性能均已认证。

## 公开文档与本地记录

公开说明使用项目相对路径、环境变量和占位符。实际用户名、绝对安装路径、本机配置、备份位置及安装执行记录保留在本地，不提交到 GitHub。本地工单与审查日志放在已忽略的 `.scratch/`，会话数据放在已忽略的 `.data/`。
