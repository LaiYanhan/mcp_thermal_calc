# Handoff: JSON 配置重构 (Pure JSON Declarative Formulas & Pipelines)

## 1. 目标与背景 (Context & Goal)
本项目已从原先的“通过修改 Python 代码和模板支持扩展”重构为“通过纯 JSON 配置原子公式、输入输出变量及计算管道（DAG）”。
所有方案已经过多轮技术推演（Grilling）与领域建模（Domain Modeling）严格对齐，重构规范已在 `.scratch/` 中就绪。

6 张工单已于 2026-10-18 在 `refactor/json-pipeline-and-formulas` 分支实现；保留在当前分支供审核，尚未合并 `main`。完整回归 108 项通过；两个基准场景的全部默认输出与迁移前严格相等。

---

## 2. 核心红线与不可动摇的设计决策 (Non-Negotiables)
在开发实现时，必须严格遵守以下已定决策：

1. **零 Python 代码关联（绝对隔离）**：
   - 新架构**严禁**与现有的 `pipelines/*.py` 文件产生任何代码关联；
   - 彻底废除 `import pipelines` 以及 `importlib.util.spec_from_file_location` 动态回退查找 `.py` 文件的逻辑；
   - 严禁出现“找不到 JSON 就重定向回 Python 文件”的兼容代码，基准场景完全由自包含的 JSON 文件驱动。
2. **彻底删除物理数值范围审查**：
   - 彻底移除 `Pin.validate()` 和 `InputConstraint.validate()` 中针对 `min_value`/`max_value` 的越界抛错逻辑；
   - 移除物性查表黑盒中的水汽相态越界报错拦截；
   - 有限数值可进入计算；除零、非有限结果及物性库自身不可解状态仍返回实际错误，不保证所有有限输入都有可求解结果。引脚中的 `min_value`/`max_value` 仅作为前端 UI 滑块/提示元数据。
3. **严格保留人机协同状态机守卫**：
   - `core/state_machine.py` 的完整流转保持不变：`SCENARIO_PROPOSED` → `confirm_scenario` → `SCENARIO_CONFIRMED` → `inspect_and_validate_parameters` → `PARAMETERS_INSPECTED` → `confirm_parameters` → `PARAMETERS_CONFIRMED` → `execute_calculation` → `CALCULATED`；未经人工确认严禁执行计算。
4. **前端 100% 视觉效果与功能零变动**：
   - 前端画布（`ui_prototype.html`、`ui_editor.js`）零修改；
   - 后端通过 JSON 资产加载构建的会话视图（`get_session_view`）与原 API 保持 100% 字段级契约兼容，四色标注、DAG 连线、拓扑波浪布局由 JSON 数据无感驱动。
5. **公式命名明确物理计算含义并解耦业务**：
   - 公式存放在 `formulas/` 目录下，文件命名格式为 `formulas/<中文计算含义>_<英文标识>.json`（如 `formulas/蒸汽进出口焓差_enthalpy_diff.json`）；
   - 公式作为通用物理/选型/经济计算单元，严禁与具体业务场景（如熔盐供汽、热泵）强绑定。

---

## 3. 核心参考制品索引 (Artifact References)
详细需求与任务拆解请直接查阅以下文件，避免二次推演：

- **重构技术规范 (Spec)**:
  `.scratch/json-pipeline-formula-refactor/spec.md`
- **执行工单列表 (Tickets)**:
  - `.scratch/json-pipeline-formula-refactor/issues/01-core-handler-registry-and-numerical-review-removal.md` (**已完成**)
  - `.scratch/json-pipeline-formula-refactor/issues/02-json-formula-engine-and-formulas-migration.md`
  - `.scratch/json-pipeline-formula-refactor/issues/03-json-pipeline-engine-and-baseline-pipelines-cutover.md`
  - `.scratch/json-pipeline-formula-refactor/issues/04-mcp-json-schema-and-state-machine-preservation.md`
  - `.scratch/json-pipeline-formula-refactor/issues/05-frontend-api-compatibility-and-regression-testing.md`
  - `.scratch/json-pipeline-formula-refactor/issues/06-adr-0014-and-glossary-synchronization.md`
- **领域术语词汇表**: `GLOSSARY.md`
- **架构决策记录**: `docs/adr/`
- **Agent 配置规则**: `AGENTS.md` 及 `docs/agents/*.md`

---

## 4. 后续维护

- 6 张工单均已完成；新增业务先复用目录中的 JSON，按 [项目 Skill](skills/thermal-calculation-agent/SKILL.md) 的人工确认流程提议或注册。完整定义示例见 [JSON 注册参考](skills/thermal-calculation-agent/references/json-definitions.md)。
- 修改核心计算或加载行为时，沿用已约定的引擎、状态机、HTTP 与数值边界测试接口；新 handler 同时声明输入输出名称及单位契约。探索工况允许进入计算，但仍验证真实的不可解错误。
- 手工修改 JSON 后重启；MCP 注册即时生效。已有 ID 的不同定义不能通过另存一份 JSON 覆盖。更新部署时同时同步 Skill 主文档与参考文件，重启旧 MCP 进程刷新工具 schema。
- 原子公式及管道保存在资产根目录，工程草稿和布局位于数据目录；历史 `.data/` 定义转换属于单独维护任务。安装及同步说明见 [installation-check.md](docs/installation-check.md)。

## 5. 本轮交接结果

- 25 个原子公式及 2 个自包含场景已迁入 JSON；启动入口为 `core/catalog.py`。
- 扩展注册工具使用严格 JSON schema，文件直接写入资产目录；Python 模板与场景回退加载均已移除。
- 前端 `ui_prototype.html`、`ui_editor.js` 与 `core/state_machine.py` 保持原样。
- 参见 ADR-0014、README 和更新后的项目技能说明；历史 `.data/` 资产未转换。
- 范围提示不拦截有限输入；除零、非有限结果及物性库不可求解状态仍返回真实错误。
- 两轴独立审查及修复后复审已完成，无遗留项；验证与审查详情见 [review.md](.scratch/json-pipeline-formula-refactor/review.md)。
- 项目 Skill、本机安装副本及 Markdown 说明已同步为 JSON 架构；主 Skill 保留六步确认流程，扩展示例独立放在 `references/json-definitions.md`。文档示例校验与 8 项接口相关回归通过，安装副本同步前已备份；旧 MCP 进程需重启才加载新接口。
