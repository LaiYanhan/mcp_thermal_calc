---
name: thermal-calculation-agent
description: 使用 thermal-calc-sizing MCP 进行熔盐储能与工业热工选型、能耗和经营毛利差额测算，并以 JSON 扩展公式及计算管道。严格执行场景与参数的人工确认，全部数值由工具计算。
---

# 熔盐储能与热工测算智能体指南

通过 MCP 查询 JSON 原子公式与计算管道，向工程师解释工况、核对参数并交付工具返回的成果。所有会话操作使用同一个 `session_id`。

## 工程边界

- 焓值、功率、热量、盐量、设备规格和经营数据均使用 MCP 返回值。缺少公式或场景时，先设计并审核 JSON 定义；不由模型心算、估算或补造结果。
- 场景与参数分别取得人工确认。注册成功、打开编辑器、默认值齐全以及前一次计算授权，均不能代替当前工况的确认。
- 展示参数的中文含义、变量标识、数值、单位及来源；有参考范围时说明它是提示信息。压力使用 MPa 绝压，表压或不同倍率单位须显式换算后提交。
- 工具只检查有限数值、引脚、单位、依赖和授权等契约，不承担物理合理性审查。范围、熔盐温区及水汽相态不会在应用层阻断探索；除零、非有限结果及 IAPWS-95 无法求解的状态仍报告实际错误。

## 六步业务流程

```text
需求 → 目录匹配或设计 JSON 场景 → 场景提议
                               ↓
                         人工确认场景
                               ↓
                    参数检查、默认值核对与补缺
                               ↓
                         人工确认参数
                               ↓
                      工具执行 → 结构化成果
```

### 1. 查询并提议场景

先调用 `list_scenarios()`；需要核对节点时调用 `list_formulas()`。两个目录的 `definition` 字段提供完整 JSON。根据实际拓扑与假设选择场景，例如基准电加热储热供汽场景 `scenario_electric_heater_salt_steam`，或给定 COP 的简化热泵场景 `scenario_industrial_heat_pump_steam`。

调用 `match_or_propose_scenario(session_id=..., user_requirements=..., scenario_id=..., initial_inputs=...)`。一次性新场景则传 `new_scenario_def=JSON对象`，与 `scenario_id` 二选一；该提议保存到会话，不等同于注册为全局资产。需要扩展时阅读下方的 JSON 扩展说明。

检查返回的 `status`、`error`、`editor_url` 和 `editor_error`。成功提议进入 `SCENARIO_PROPOSED` 后，向人类展示实际选用的场景、关键假设、拓扑与可用编辑器链接，等待场景确认。编辑器启动失败不代表提议失败，也不能宣称页面已经打开；端口冲突时按返回错误处理。

### 2. 记录人工场景确认

收到明确同意后调用 `confirm_scenario(session_id=..., confirmed=True, feedback=...)`；收到异议则传 `confirmed=False`，按意见修改后重新提议和确认。已有授权只适用于当时审核的场景和公式。

### 3. 核对参数与补缺

调用 `inspect_and_validate_parameters(session_id=..., parameters=...)`，读取 `is_complete`、`parameters_summary`、`defaults_applied` 和 `missing_inputs`。默认值取自当前管道 JSON 的 `required_inputs`；不从 Python 常量模块另行补查或把默认值当作用户已确认的值。

缺项时逐项说明物理含义及单位，请人类补充，再次检查。齐全时进入 `PARAMETERS_INSPECTED`，调用 `open_pipeline_editor(session_id=..., stage=2)`，向人类展示工具返回的参数表及编辑器链接，明确标注用户提供值、默认值和工程常量，等待参数确认。

### 4. 记录人工参数确认

收到对当前参数的明确计算授权后，调用 `confirm_parameters(session_id=..., confirmed=True, feedback=...)`，检查状态为 `PARAMETERS_CONFIRMED`。拒绝时传 `confirmed=False` 并按意见修改。

修改参数会清除旧结果与参数授权；修改拓扑或相关全局公式需要重新确认场景。参数发生变化后，重新检查、展示和确认，不能因输入事件自动计算。

### 5. 执行工具计算

调用 `execute_calculation(session_id=...)`，检查返回是否为 `CALCULATED`。失败时解释工具原始错误，修正输入或定义，并依据变更重新走确认流程。

`solve_atomic_formula(formula_id=..., known_variables=..., target_variable=..., session_id=...)` 同样受当前会话授权与已确认工况限制，不能作为绕过流程的独立计算入口。

### 6. 交付实际成果

以 `result.results` 为完整成果来源，包括中间结果；保留 `step_id`、`formula_id`、变量、中文含义、单位和值，以区分同一公式的多次使用。`final_outputs` 是计算输出的变量值索引，人工输入及工程常量另在 `initial_inputs` 中。

可按实际产生的设备规格、储热量、运行能耗和经营毛利差额整理报告。只报告本场景存在的成果，不固定要求电加热器、变压器或某个盐量裕度，不把输入列为计算成果，也不创建引擎已移除的输出分组或摘要字段。经营毛利差额不包含折旧、贷款与税费。

## JSON 场景与公式扩展

需要新增、微调或持久化场景/公式时，阅读 [JSON 定义与注册示例](references/json-definitions.md)。该参考提供可校验的公式、经验 handler 和自包含管道示例；实际工具 schema 及目录定义为接口依据。

先展示变更的数学关系、引脚单位、节点来源和工程假设。取得人类对定义的明确审核后，才向注册工具传 `human_approved=True`。新变体使用独立 ID；注册工具拒绝已有 ID，原地编辑使用前端算子接口或修改已审核的 JSON 后重启。

MCP 注册直接写入资产 JSON 并即时生效；手工修改文件后须重启服务。启动时先发现公式，再校验和发现管道。JSON 只能引用已注册的物性/选型 handler，其输入输出名称和单位须匹配；新 handler 需要单独开发、验证核心代码。

## 持久化与编辑器

- 默认资产目录为项目 `formulas/` 与 `pipelines/`，可由 `THERMAL_CALC_ASSET_DIR` 指定资产根目录；会话草稿、参数及布局位于 `.data/sessions/`，由 `THERMAL_CALC_DATA_DIR` 指定数据目录。
- 历史 `.data/operators.json` 和 `.data/pipelines/` 不再由新目录加载器读取，保留文件不等于已迁入资产；需要的定义单独审核转换。恢复会话草稿不会恢复旧计算结果或授权。
- 正常模式由 Agent 调用 `open_pipeline_editor(session_id=..., stage=1或2)` 控制阶段；阶段 02 先完成场景确认。切换展示阶段本身不执行计算。
- 独立调试使用 `.venv/Scripts/python.exe run_web.py --debug --pipeline <JSON路径或ID>`；`--stage 2` 需配合 `--debug`。MCP 编辑器固定使用 8765 端口，若同时运行独立 Web，先停止它或为独立 Web 指定其他 `--port`。调试模式也须显式确认后计算。
