# Skill、JSON 资产与 MCP 安装检查

更新日期：2026-10-18（Asia/Shanghai）。本页反映 JSON 重构完成后的运行与安装方式；早期 Python 模板和 `.data` 资产加载说明已停用。

## 当前实现与验证依据

- 业务入口包含 11 个 MCP 工具，内置 2 个自包含 JSON 场景、25 个 JSON 原子公式。
- 重构完成及后续独立审查时，完整 pytest 回归均为 **108 项通过**，其中包含 Node.js 前端行为测试和真实 MCP stdio 子进程测试；两个默认场景的全部输出与迁移前基线严格相等。
- `tests/test_mcp_stdio.py` 覆盖严格 JSON 公式/管道注册、目录发现和人工确认后的执行，注册本身不授予计算权限。协议测试使用隔离资产及数据目录，不打开用户浏览器。
- 文档中的 JSON 示例通过当前 Pydantic 定义、公式构造和管道契约校验。项目 Skill 与安装副本通过 Skill Creator `quick_validate.py`，两份 Skill 及参考文件内容一致。
- 本轮文档同步核对了 3 个完整 JSON 示例、修改文档的本地链接以及 CLI `--help` / `--list`；MCP stdio 与编辑器阶段控制的 8 项相关回归通过。`uv pip check` 确认当前依赖兼容；未修改计算代码或新增项目依赖。
- 实现与独立审查记录见 [交接文档](../HANDOFF.md) 及 [重构审查记录](../.scratch/json-pipeline-formula-refactor/review.md)。测试证据不代表所有工业场景或设备性能均已认证。

## 本机安装记录

既有 MCP 配置位于 `C:/Users/ASUS/.codex/config.toml`，服务名为 `thermal-calc-sizing`，以项目 `.venv/Scripts/python.exe` 启动 `server/mcp_server.py` 的绝对路径。UTF-8 环境变量为 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`；`THERMAL_CALC_DATA_DIR` 指向项目 `.data`。

项目 Skill 源为 `skills/thermal-calculation-agent/`，本机安装目录为 `C:/Users/ASUS/.codex/skills/thermal-calculation-agent/`。本轮同步主文档与 `references/json-definitions.md`，同步前的安装副本保存在用户 Codex 目录的 `backups/thermal-calculation-agent/` 下。本轮未修改 MCP 配置或重启用户正在运行的服务；首次安装命令见 [README](../README.md)。

旧 MCP 进程仍使用启动时的代码与 schema。重启服务；若客户端工具缓存未刷新，再重启 Codex 并新建聊天。检查注册工具出现 `formula_definition`、`pipeline_definition`，不再使用 `formula_code`、`pipeline_code` 或 `sub_category`。Skill 主文档和参考文件应作为同一版本同步；当前轮已加载的旧指令不会因磁盘文件更新而自动改写。

## 已安装 Skill 的后续同步

在项目根目录执行以下 PowerShell 命令，仅备份并同步该 Skill。保留安装目录中的其他本地资源，备份位于技能发现目录之外：

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

## 资产、会话与后续维护

公式和已注册管道位于项目 `formulas/`、`pipelines/`；可用 `THERMAL_CALC_ASSET_DIR` 指定包含这两个目录的资产根目录。启动时先递归发现公式，再发现管道，重复 ID 或无效定义会阻止加载。MCP 注册校验后原子写入 JSON 并即时注册；手工改文件后重启。

`.data/sessions/` 保存会话草稿、参数与布局；重启后需重新确认。历史 `.data/operators.json`、`.data/pipelines/` 不再自动加载，也未被本轮转换或删除。需要的历史定义应另行审核转为标准 JSON；只设置 `THERMAL_CALC_DATA_DIR` 不会改变资产目录。

编辑器阶段由 AI 显式调用 `open_pipeline_editor` 控制，前端控制只在 `run_web.py --debug` 时启用；微调参数不即时重算。MCP 编辑器使用 8765 端口；若独立 Web 同时运行，给它指定其他 `--port`。热泵基准使用给定 COP，未建模热源侧或设备性能曲线。范围、熔盐温区及水汽相态不再由应用层拦截；工程判断和两次人工确认仍由使用者完成。
