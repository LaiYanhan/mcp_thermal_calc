# 工业熔盐储热与热工选型测算系统 (MCP Thermal Calculation & Sizing Engine)

为企业构建的确定性工程热工计算、离散设备规格选型与经济性测算 MCP 工具服务与 Agent 技能体系。

##  系统核心特性与架构原则
1. **AI 严禁私自计算（100% 确定性程序执行）**：所有热工物性（IAPWS-95）、能量守恒、设备选型与电费测算完全由 Python 核心计算，彻底杜绝大模型计算幻觉；
2. **分阶段状态机与人工确认强守卫**：在 MCP 工具层内置状态机，必须经历“场景确认 $\rightarrow$ 参数缺项补全 $\rightarrow$ 参数审核确认 $\rightarrow$ 授权计算”，未经授权调用计算将被直接物理拦截；
3. **公式解耦与符号双向推导（SymPy）**：代数公式基于 SymPy 符号方程构建，天然支持正向与逆向多变量推导（如 $a,b \Rightarrow c$ 或由目标 $c$ 逆推所需入参 $a$）；水蒸气状态方程单向查表封装；
4. **统一原子公式化与管道装配（无过度抽象）**：设备选型与阶梯造价规则均抽象为纯净原子公式，在 `pipelines/` 声明式 DAG 管道中与热工物理公式串联一体；
5. **高度可扩展性**：支持通过声明式 JSON 或受限标准模板注册新公式与新计算管道。定义经校验后以数据形式保存，立即进入注册表，重启时重新加载。

---

##  目录结构

```
.
├── GLOSSARY.md               # 领域统一词汇表 (Domain Glossary)
├── docs/adr/                 # 架构决策记录
├── constants/                # 独立工程常量与默认参数库
│   ├── default_parameters.py # 默认工况参数基准表（含中文释义与单位）
│   ├── molten_salt.py        # HITEC/太阳盐热物性状态方程 (密度/导热/粘度/比热)
│   └── equipment_catalog.py  # SGS/电加热器/国标变压器规格序列与阶梯造价函数
├── core/                     # 核心计算与调度引擎
│   ├── types.py              # Pin/引脚、FormulaMetadata、PipelineStep 等类型定义
│   ├── formula.py            # AlgebraicFormula (SymPy双向)、EmpiricalFormula 与注册表
│   ├── pipeline.py           # Pipeline DAG 拓扑执行引擎与校验
│   └── state_machine.py      # 分阶段状态机与人工确认守卫控制器
├── formulas/                 # 原子公式库 (按业务解耦)
│   ├── thermal/              # 水蒸气物性查表、焓差、SGS功率、储热量、电加热器功率、熔盐量
│   ├── operation/            # 用电量、供汽量、购电成本、售汽收入、日度/年化毛收益差额
│   └── sizing/               # SGS规格整定、电加热器整定、主变压器查表选型、熔盐采购量整定
├── pipelines/                # 场景计算管道库 (声明式 DAG)
│   ├── electric_heater_salt_steam.py   # 基准场景：电加热器熔盐储热供汽流水线
│   └── industrial_heat_pump_steam.py  # 工业热泵储能供汽（给定 COP 的简化模型）
├── server/                   # MCP 服务端接口层
│   └── mcp_server.py         # 基于 MCP 2.x SDK 暴露的 11 个工程与工作流工具
├── skills/                   # 智能体交互技能说明书
│   └── thermal-calculation-agent/SKILL.md # 指导大模型执行状态机流程的详细规范
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

Skill 在后续轮次可被发现；若 MCP 工具列表尚未刷新，重启 Codex 后新建聊天。可用 `$thermal-calculation-agent` 指定技能。项目目录是安装后的运行源，移动项目后应重新注册 MCP；修改 Skill 后需同步安装副本。

真实 stdio 集成回归见 `tests/test_mcp_stdio.py`，覆盖握手、工具发现、未授权计算拦截和确认后的完整计算。测试使用临时数据和自动化确认样例，不打开浏览器。

### 4. 使用本地编辑器
```bash
.venv\Scripts\python run_web.py
```

默认由 AI 通过 `open_pipeline_editor(session_id=..., stage=2)` 切换到阶段 02；已打开的同会话页面会同步阶段命令与计算结果。前端阶段切换及确认计算按钮仅在独立调试时启用：

```powershell
.\.venv\Scripts\python.exe run_web.py --debug --pipeline pipelines/electric_heater_salt_steam.py
```

`--stage 2` 必须配合 `--debug`。参数微调只保存参数并使旧结果和授权失效；正常模式由 AI 重新核对参数、获得人工确认后执行计算，调试模式需显式点击确认计算。输入或保存参数均不会自动重算。
从 MCP 打开编辑器时，由 MCP 进程启动同一份 Web 服务；此时不用另开 `run_web.py`。编辑器仅监听本机，浏览器写入必须同源。

独立调试可用 `run_web.py --list` 查看流水线，或用 `run_web.py --pipeline <ID或模块路径> --reset` 从代码定义重新打开。场景选择与重置仅用于页面首次加载；成功后会移除地址中的 `reset`，后续保存、确认、计算和刷新继续使用当前会话。

自动排版根据当前流水线的真实依赖向右展开、分支向下排列，不依赖蒸汽场景的参数或步骤名称。输入与常量保持胶囊样式，拖拽位置仍会保存；“恢复默认排版”重新计算当前拓扑的位置。

先确认场景拓扑，再核对参数并点击“确认参数并计算”。修改参数后清除旧结果；修改拓扑或相关全局算子后，需重新确认场景。未连接的引脚可以保存为草稿，但不能确认或计算。算子抽屉中的来源下拉用于重接引脚，新增常量会成为真实管道输入。前端不执行热工或经营计算。

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

场景专用参数校验在 Python 流水线的 `input_constraints` 中声明。例如 `InputConstraint(variable="upper", greater_than="lower", message="上限必须大于下限")`，或使用 `min_value`、`max_value` 声明范围（从 `core.types` 导入 `InputConstraint`）。约束引用流水线输入名称；修改名称时同步修改约束。核心只执行显式约束，不根据参数名称推断业务规则。熔盐场景的规则位于 `pipelines/validation.py`，旧工程的 `salt_profile` 字段由该业务模块注册的转换方法处理；约束随会话保存与恢复，AI 场景目录也会返回约束。

会话、布局、自定义管道与全局算子修改默认保存在 `.data/`，可通过 `THERMAL_CALC_DATA_DIR` 指定其他目录。重启恢复工程草稿与参数，授权和旧计算结果不跨进程恢复。内置 Python 公式仍位于 `formulas/`，动态注册不会执行或覆盖 Python 源文件。

新增代数算子必须提供 `id`、`name`、`equation`、`inputs` 和 `outputs`；每个引脚需明确 `name`、`description`、`unit`。表达式支持变量、有限数值和 `+ - * / **`，必须具有唯一正向输出；禁止导入、函数调用和属性访问。已有物性/查表算子的计算实现不能通过代数文本编辑。

压力输入统一采用 **MPa 绝压**；表压须由调用者依据现场大气压换算。带单位输入可使用 `{"value": 1.5, "unit": "MPa"}`，不同倍率单位需显式换算。基准 HITEC 场景校验盐种温区与正温差；水蒸气查表校验液/汽相边界，不支持用温度、压力猜测湿蒸汽干度。
