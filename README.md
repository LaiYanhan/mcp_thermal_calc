# 工业熔盐储热与热工选型测算系统 (MCP Thermal Calculation & Sizing Engine)

为企业构建的确定性工程热工计算、离散设备规格选型与经济性测算 MCP 工具服务与 Agent 技能体系。

当前版本使用 JSON 原子公式和自包含管道，内置 25 个公式、2 个场景。业务流程见 [项目 Skill](skills/thermal-calculation-agent/SKILL.md)，扩展示例见 [JSON 定义与注册](skills/thermal-calculation-agent/references/json-definitions.md)，实现与审查状态见 [HANDOFF.md](HANDOFF.md)。

##  系统核心特性与架构原则
1. **AI 严禁私自计算（100% 确定性程序执行）**：所有热工物性（IAPWS-95）、能量守恒、设备选型与电费测算完全由 Python 核心计算，彻底杜绝大模型计算幻觉；
2. **分阶段状态机与人工确认强守卫**：在 MCP 工具层内置状态机，必须经历“场景确认 $\rightarrow$ 参数缺项补全 $\rightarrow$ 参数审核确认 $\rightarrow$ 授权计算”，未经授权调用计算将被直接物理拦截；
3. **公式解耦与符号双向推导（SymPy）**：代数公式基于 SymPy 符号方程构建，天然支持正向与逆向多变量推导（如 $a,b \Rightarrow c$ 或由目标 $c$ 逆推所需入参 $a$）；水蒸气状态方程单向查表封装；
4. **统一原子公式化与管道装配（无过度抽象）**：设备选型与阶梯造价规则均抽象为纯净原子公式，在 `pipelines/` 声明式 DAG 管道中与热工物理公式串联一体；
5. **高度可扩展性**：使用严格 JSON 注册新公式与自包含计算管道。启动时自动扫描资产目录；MCP 注册校验后写入 JSON 文件并立即生效。

---

##  目录结构

```
.
├── GLOSSARY.md               # 领域统一词汇表 (Domain Glossary)
├── docs/adr/                 # 架构决策记录
├── constants/                # 独立工程常量与默认参数库
│   ├── default_parameters.py # 历史基准资料；运行时默认值以内联 JSON 为准
│   ├── molten_salt.py        # HITEC/太阳盐热物性状态方程 (密度/导热/粘度/比热)
│   └── equipment_catalog.py  # SGS/电加热器/国标变压器规格序列与阶梯造价函数
├── core/                     # 核心计算与调度引擎
│   ├── types.py              # Pin/引脚、FormulaMetadata、PipelineStep 等类型定义
│   ├── formula.py            # AlgebraicFormula (SymPy双向)、EmpiricalFormula 与注册表
│   ├── pipeline.py           # Pipeline DAG 拓扑执行引擎与校验
│   ├── definitions.py        # 严格 Pydantic JSON 契约
│   ├── handlers.py           # IAPWS-95 与设备选型处理函数白名单
│   ├── catalog.py            # 先加载公式 JSON，再加载管道 JSON
│   └── state_machine.py      # 分阶段状态机与人工确认守卫控制器
├── formulas/                 # <中文计算含义>_<英文标识>.json；通用原子公式
├── pipelines/                # 自包含的 JSON DAG，内联输入、常量和默认值
│   ├── scenario_electric_heater_salt_steam.json
│   └── scenario_industrial_heat_pump_steam.json
├── preview/
│   └── pipeline_editor_preview.html # 正式编辑器页面，由服务直接读取，无重定向
├── ui_editor.js              # 编辑器渲染与交互脚本
├── server/                   # MCP 服务端接口层
│   └── mcp_server.py         # 基于 MCP 2.x SDK 暴露的 11 个工程与工作流工具
├── skills/                   # 智能体交互技能说明书
│   └── thermal-calculation-agent/ # SKILL.md 与按需阅读的 references/JSON 示例
└── tests/                    # 单元与回归测试套件
```

---

##  启动与使用指南

### 1. 安装依赖（Windows PowerShell）
需要 Python 3.13 和 `uv`。已验证的运行依赖在 `requirements.txt`，测试依赖在 `requirements-dev.txt`；前端测试还需要 PATH 中的 Node.js。首次安装：
```powershell
uv venv --python 3.13 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements-dev.txt
```
已有虚拟环境时跳过创建命令。仅运行服务可改用 `requirements.txt`。

### 2. 运行自动化测试与数据回归核对
```powershell
.\.venv\Scripts\python.exe -m pytest -v tests/
```
前端回归使用 Node.js（`node --test tests/test_editor.js`），完整 pytest 会一并运行。测试数据写入独立临时目录。

### 3. 启动 MCP 服务
```bash
.venv\Scripts\python server/mcp_server.py
```
可直接配置到 Claude Desktop、Cursor 或企业级 Agent 编排系统中。

#### 安装到本机 Codex

在项目根目录执行以下 PowerShell 命令。服务使用绝对路径启动，不依赖聊天工作目录；UTF-8 环境变量保证中文协议响应正常。Skill 安装到用户技能目录，MCP 使用独立服务名 `thermal-calc-sizing`。

```powershell
$projectRoot = (Get-Location).Path
$codexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
codex mcp add thermal-calc-sizing --env PYTHONUTF8=1 --env PYTHONIOENCODING=utf-8 --env "THERMAL_CALC_DATA_DIR=$projectRoot\.data" -- "$projectRoot\.venv\Scripts\python.exe" "$projectRoot\server\mcp_server.py"
$skillTarget = Join-Path $codexRoot 'skills\thermal-calculation-agent'
if (Test-Path $skillTarget) { throw "Skill 目录已存在，请先备份再更新：$skillTarget" }
New-Item -ItemType Directory -Path (Split-Path $skillTarget) -Force | Out-Null
Copy-Item -LiteralPath "$projectRoot\skills\thermal-calculation-agent" -Destination $skillTarget -Recurse
codex mcp get thermal-calc-sizing
```

已有安装的更新方式见 [安装与同步检查](docs/installation-check.md)。同步时保留备份，并同时更新 `SKILL.md` 与其 `references/`，避免主文档链接到旧版或缺失参考。Skill 在后续轮次可被发现；若 MCP 工具列表尚未刷新，重启服务或 Codex 后新建聊天。可用 `$thermal-calculation-agent` 指定技能。项目目录是安装后的运行源，移动项目后应重新注册 MCP；本次 JSON 注册接口也需要重启原 MCP 进程才能生效。

真实 stdio 集成回归见 `tests/test_mcp_stdio.py`，覆盖握手、工具发现、未授权计算拦截和确认后的完整计算。测试使用临时数据和自动化确认样例，不打开浏览器。

### 4. 使用本地编辑器

HTML 源文件统一位于 `preview/pipeline_editor_preview.html`，原根目录 `ui_prototype.html` 已移入该位置，原预览重定向已移除。服务仍通过 `/` 和 `/editor` 直接返回完整页面，脚本路径保持 `/ui_editor.js`。
```bash
.venv\Scripts\python run_web.py
```

默认由 AI 通过 `open_pipeline_editor(session_id=..., stage=2)` 切换到阶段 02；已打开的同会话页面会同步阶段命令与计算结果。前端阶段切换及确认计算按钮仅在独立调试时启用：

```powershell
.\.venv\Scripts\python.exe run_web.py --debug --pipeline pipelines/scenario_electric_heater_salt_steam.json
```

`--stage 2` 必须配合 `--debug`。参数微调只保存参数并使旧结果和授权失效；正常模式由 AI 重新核对参数、获得人工确认后执行计算，调试模式需显式点击确认计算。输入或保存参数均不会自动重算。

阶段 02 在场景确认后提供“预览计算”按钮，正常模式和调试模式均可使用。点击后由后端计算当前页面参数（含尚未保存的输入），画布显示带“仅供参数核对”提示的临时数值。预览不保存参数、不记录人工确认、不改变会话状态，也不写入或替换正式计算结果；参数或计算上下文变化后预览失效。AI 仍须按原流程取得人工确认并执行正式计算，才能提供正式完整成果。

预览使用独立的 `POST /api/preview_calculation`，请求为 `{pipeline, parameters}` 页面快照，响应为 `preview_result`；接口不读取或写入会话，也不作为 MCP 工具暴露。正式计算仍使用原有受状态守卫保护的接口。边界说明见 [ADR-0015](docs/adr/0015-ephemeral-editor-calculation-preview.md)。

从 MCP 打开编辑器时，由 MCP 进程启动同一份 Web 服务；此时不用另开 `run_web.py`。编辑器仅监听本机，浏览器写入必须同源。

独立调试可用 `run_web.py --list` 查看流水线，或用 `run_web.py --pipeline <ID或JSON路径> --reset` 从 JSON 定义重新打开。场景选择与重置仅用于页面首次加载；成功后会移除地址中的 `reset`，后续保存、确认、计算和刷新继续使用当前会话。

自动排版根据当前流水线的真实依赖向右展开、分支向下排列，不依赖蒸汽场景的参数或步骤名称。输入与常量保持胶囊样式，拖拽位置仍会保存；“恢复默认排版”重新计算当前拓扑的位置。

正常模式先由 Agent 记录人工场景确认，再核对参数、记录人工参数确认并调用计算工具；独立 `--debug` 模式通过按钮完成相同步骤。修改参数后清除旧结果；修改拓扑或相关全局算子后，需重新确认场景。未连接的引脚可以保存为草稿，但不能确认或计算。算子抽屉中的来源下拉用于重接引脚，新增常量会成为真实管道输入。前端不执行热工或经营计算。

点击代数算子，在抽屉的“本次计算”中选择待求参数，其他参数自动成为已知量。保存后重新确认场景并填写新增输入；也可在来源下拉中连接其他节点结果。卡片显示当前求解方向的中文公式，原有代数编辑框仍使用英文变量标识。物性/查表算子保持单向计算。

AI 可先调用 `list_formulas` 查看 `variables` 中的中文含义、单位和范围，以及 `solve_targets` 中可选择的变量，再在场景的步骤中配置求解方向。例如：

```json
{
  "step_id": "steam_flow",
  "formula_id": "thermal.theoretical_power",
  "solve_target": "steam_mass_flow",
  "input_map": {"theoretical_power": "requested_power", "enthalpy_diff": "enthalpy_diff"},
  "output_map": {"steam_mass_flow": "steam_mass_flow"}
}
```

其中 `requested_power` 和 `enthalpy_diff` 必须来自场景输入或其他步骤输出；省略 `solve_target` 使用公式默认方向。同一公式 ID 可在多个步骤中分别求解不同参数。

全部步骤的公式输出自动成为结构化成果，包括中间结果。`results` 提供步骤、公式、参数含义、单位和值，`final_outputs` 提供计算输出的变量值索引，输入和常量另存于 `initial_inputs`。不再需要成果分组或输出清单；旧 JSON 中的成果分组字段读取时忽略，旧的设备/经营摘要字段不再返回。

`min_value` / `max_value` 仅用于界面参考和滑块提示，不阻断有限数值计算。旧 `input_constraints` 仍可保存和展示，其范围与大小关系不再拦截；变量引用和单位契约仍须有效。熔盐温区和水汽液/汽相的应用层拦截已移除。除零、非有限结果和 IAPWS-95 自身无法求解的状态仍会报告计算错误，不进行夹值、替代模型或结果填充。

会话草稿、参数与画布布局保存在 `.data/`（`THERMAL_CALC_DATA_DIR` 可重定向）。公式与注册管道直接保存在 `formulas/`、`pipelines/`，由 `core/catalog.py` 在服务启动时递归加载，路径不依赖工作目录；`THERMAL_CALC_ASSET_DIR` 可指定独立的资产根目录。前端算子原地修改同样更新公式 JSON。重启恢复草稿，授权和旧结果不跨进程恢复。本次不迁移历史 `.data/operators.json` 或 `.data/pipelines/` 资产；需要的历史定义应另行审核转换为严格 JSON。

MCP `register_new_formula(formula_definition=JSON对象, filename="中文计算含义_english_id.json", human_approved=True)` 和 `register_new_pipeline(pipeline_definition=JSON对象, pipeline_filename="scenario_id.json", human_approved=True)` 接受工具 schema 定义的结构化对象；`human_approved=True` 需要工程师明确审核，注册成功不替代会话确认。`list_formulas` 和 `list_scenarios` 的 `definition` 字段提供完整定义。代数定义包含 `formula_type="algebraic"`、`expression`、`inputs`、`outputs`；经验定义包含 `formula_type="empirical"` 及白名单 `handler`。管道在 `required_inputs` 中内联默认值和 `kind`，在 `steps` 中连接已有公式。文件新增后重启可自动发现；MCP 注册即时生效；不执行 Python 模板。

标准 JSON 代数定义使用 `id`、`name`、`category`、`formula_type="algebraic"`、`expression`、`inputs`、`outputs`。前端 `/api/operator/add` 保留 `equation` 字段，后端转换为标准 JSON；两类载荷不能混用。每个引脚明确 `name`、`description`、`unit`。表达式支持变量、有限数值和 `+ - * / **`，必须具有唯一正向输出；禁止导入、函数调用和属性访问。经验公式的引脚名称及单位必须匹配白名单 handler；已有物性/选型算子的计算实现不能通过代数文本编辑。

会话接口沿用单数路径 `GET /api/session/{session_id}` 与 `POST /api/session/{session_id}/pipeline`。`match_or_propose_scenario` 的 `new_scenario_def` 仅用于当前会话提议；全局复用需通过注册工具保存，或手工保存审核后的 JSON 并重启。示例和字段边界见 [JSON 定义与注册](skills/thermal-calculation-agent/references/json-definitions.md)。

通用工程数据由场景 JSON 的 `data_tables` 自包含保存，公式通过 `data_inputs` 声明数据端口，节点用 `data_map` 绑定同场景表 ID。`data.fixed_step`、`data.discrete` 和 `data.piecewise` 分别提供固定步长整定、离散档位整定及分段取值；两种整定均支持 `ceil`、`floor`、`nearest`，中点半入，查表超界取首末行。新增同类数据只改 JSON；单值常量继续使用 `required_inputs` 和 `kind="constant"`。现有设备专用 handler 保留为旧定义兼容入口，新数据使用通用规则。表和绑定随目录、保存及会话快照完整往返，修改表后沿用原有重新确认流程。字段与中性示例见上述 JSON 说明；加载方式、IAPWS95、人工确认及预览边界沿用现有行为。

压力输入统一采用 **MPa 绝压**；表压须由调用者依据现场大气压换算。带单位输入可使用 `{"value": 1.5, "unit": "MPa"}`，不同倍率单位需显式换算。范围和相态信息供工程师判断；饱和边界沿用干饱和蒸汽比焓，不通过温度、压力猜测湿蒸汽干度。

`.scratch/` 是本地工单、规范和临时记录目录，已通过 `.gitignore` 排除，不随仓库上传；公开的架构决策见 `docs/adr/`。
