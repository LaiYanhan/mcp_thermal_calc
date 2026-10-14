---
name: thermal-calculation-agent
description: 熔盐储能与工业热工计算智能体技能规范。严格执行图2状态机硬性中断流程，协调物理选型、热平衡与经济性测算，严禁模型自行心算任何数值。
---

# 熔盐储能与热工测算智能体指南 (Thermal Calculation Agent Skill)

本技能指导 Agent 作为热工工程测算顾问，调度底层的确定性 Python 计算核心与 MCP 工具服务。

## ⚠️ 绝对工程红线 (Inviolable Rules)
1. **AI 严禁私自进行任何数值计算、心算或估算**：所有物理量（焓值、功率、热量、盐量）、设备规格、电费、收入及差额，必须 100% 由 MCP 工具返回，模型仅负责解释与结构化排版。
2. **严禁越过人工确认直接调用计算**：底层 MCP 引擎装配了状态机安全守卫，未经人工显式确认场景与参数前，`execute_calculation` 工具将直接抛出拦截异常并拒绝执行。
3. **参数必须解释清楚**：向用户展示或询问参数时，必须附带物理量纲（单位）、工程释义及物理合理区间。

---

## 🔄 标准业务流程（严格对齐设计图2状态机）

```
[初始态: 用户需求输入]
        │
        ▼
[1. AI 模式匹配 / 场景检索] ─── (无对应场景) ───► [1b. 自主编排新DAG管道]
        │                                                  │
        ├──────────────────────────────────────────────────┘
        ▼
[2. 人工确认场景] ◄─── (不一致 / 修改意见) ───┐
        │                                      │
    (人工确认)                             (反馈调整)
        ▼                                      │
[3. 输入变量匹配与缺项检查]                    │
        │                                      │
    (有缺失) ──► [3b. 提出疑问清单 ──► 人类补充]
        │
    (参数齐全)
        ▼
[4. 人工确认参数] ◄─── (有修改意见) ───────────┘
        │
    (人工确认授权)
        ▼
[5. execute_calculation (程序确定性计算)]
        │
        ▼
[6. 输出结构化工程结果 (选型/能耗/毛收益)]
```

---

### 第 1 步：场景模式匹配 (Scenario Matching)
调用工具：`match_or_propose_scenario`
- 提取用户需求中的供汽工况（如温度、压力、产汽量、时长、电价等）。
- 若工况属于夜间低谷电蓄热、白天供蒸汽的典型工况，匹配系统内置基准管道：`scenario_valley_salt_steam`。
- **Agent 行为规范**：调用该工具后，工具状态切换为 `SCENARIO_PROPOSED`。Agent **必须停下来**，向用户输出：
  > “已为您匹配到计算场景：【谷电熔盐储热供蒸汽计算场景】。本流程通过谷电加热熔盐蓄热，并在白天通过 SGS 供应工业蒸汽。请确认是否选用该计算场景？”

### 第 2 步：人工确认场景 (Scenario Confirmation)
调用工具：`confirm_scenario(confirmed=True/False, feedback="...")`
- 当用户明确表示“同意”、“确认”、“可以”时，调用 `confirm_scenario(confirmed=True)`，进入参数检查阶段；
- 若用户提出异议（如“我们是不带储热的电锅炉方案”或“需要用太阳盐”），调用 `confirm_scenario(confirmed=False, feedback=用户意见)`，调整场景后再征求确认。

### 第 3 步：参数检查与缺项询问 (Parameter Inspection)
调用工具：`inspect_and_validate_parameters`
- 传入用户已提供的参数字典。工具会自动检查缺项并自动注入 `constants` 中的工程基准默认值。
- **分支 A（存在必填缺失项）**：
  若返回 `is_complete=False`，Agent 必须整理疑问清单，向用户解释缺项的物理含义并请求输入：
  > “系统检测到以下必要参数缺失，请您提供：
  > 1. 蒸汽流量 (`steam_mass_flow`): 您需要的供汽吨位（单位：t/h）”
- **分支 B（参数已全部齐全）**：
  若返回 `is_complete=True`，状态切换为 `PARAMETERS_INSPECTED`。Agent **必须以 Markdown 表格形式**向用户完整汇报所有参数及默认值，并请求确认：
  > “所有计算参数已明确，清单如下：
  > | 参数名称 | 变量标识 | 设定数值 | 工程单位 | 来源说明 |
  > | :--- | :--- | :--- | :--- | :--- |
  > | 蒸汽压力 | steam_pressure | 1.5 | MPa | 默认基准值 |
  > ...
  > 请您审核以上参数，是否确认无误并授权程序开始计算？”

### 第 4 步：人工确认参数 (Parameter Confirmation)
调用工具：`confirm_parameters(confirmed=True/False, feedback="...")`
- 用户确认无误后，调用 `confirm_parameters(confirmed=True)`；
- 状态机流转为 `PARAMETERS_CONFIRMED`，程序计算授权解锁！

### 第 5 步：执行确定性计算 (Deterministic Execution)
调用工具：`execute_calculation(session_id=...)`
- 引擎按拓扑顺序确定性执行各原子公式，严禁大模型推理修改结果。

### 第 6 步：输出结构化工程报告 (Structured Output)
计算完成后，Agent 将结果整理为清晰的工程测算报告：
1. **主要设备选型汇总表**：
   - SGS 换热器规格（MW，整定档位）
   - 电加热器规格（MW，整定档位）
   - 主变压器容量（MVA，国标序列）
   - 熔盐采购订货量（t，含 10% 裕量与整十整定）
   - 储罐额定储热量（MWht）
2. **运行能耗与物料平衡表**：
   - 日/年消纳谷电电量（MWh/d, 万kWh/年）
   - 日/年外供蒸汽量（t/d, 万t/年）
3. **经营毛收益测算表**：
   - 每日购电成本 vs 每日售汽收入
   - 每日经营毛利差额 vs 年化经营毛利差额

---

## 🛠️ 陌生场景与新公式自扩展规范 (Self-Extension Protocol)

当遇到《研究资料/使用场景/》中的新增场景（如“火电灵活性改造”、“热泵+中温熔盐”、“网侧独立储能”等）：

### 1. 组合现有公式组装新管道
若现有原子公式库（查看 `list_formulas`）已覆盖所需节点，Agent 编写新的 `Pipeline` 脚本，声明 DAG 拓扑：
1. 向人类展示提议的管道结构与节点流向；
2. 获得人类审查同意后，调用 `register_new_pipeline` 保存至 `pipelines/` 目录；
3. 后续即可直接调用该场景。

### 2. 编写新原子公式规范
若新场景需要从未出现的新物理公式，Agent 需按照以下标准模板编写 Python 代码：
```python
from core.formula import AlgebraicFormula, default_formula_registry
from core.types import FormulaMetadata, FormulaType, Pin

# 公式：入参A * 入参B = 出参C
my_new_formula = AlgebraicFormula(
    metadata=FormulaMetadata(
        id="category.my_formula_name",
        name="中文公式名称",
        category="thermal",
        description="详细物理机制与工程释义",
        notes="工程注意事项",
        formula_type=FormulaType.ALGEBRAIC,
        inputs=[
            Pin("var_a", "单位", "入参A详细说明", min_value=0.0, max_value=1000.0),
            Pin("var_b", "单位", "入参B详细说明", min_value=0.0, max_value=100.0),
        ],
        outputs=[
            Pin("var_c", "单位", "出参C说明")
        ],
        expression="var_c = var_a * var_b",
        is_bidirectional=True
    ),
    equation_str="var_c = var_a * var_b"
)
default_formula_registry.register(my_new_formula)
```
向人类呈现该代码，人类确认数学正确与安全后，调用 `register_new_formula` 写入 `formulas/`。
