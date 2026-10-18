---
name: thermal-calculation-agent
description: 熔盐储能与工业热工计算智能体技能规范。严格执行状态机硬性中断流程，协调物理选型、热平衡与经济性测算，严禁模型自行心算任何数值。
---

# 熔盐储能与热工测算智能体指南

本技能指导 Agent 作为热工工程测算顾问，严格执行下述状态机与人工确认流程，调用项目现有的 Python 公式、Pipeline 流水线和 MCP 工具完成测算。

##  绝对工程红线 (Inviolable Rules)
1. **AI 严禁私自进行任何数值计算、心算或估算**：所有物理量（焓值、功率、热量、盐量）、设备规格、电费、收入及差额，必须 100% 由 MCP 工具返回，模型仅负责解释与结构化排版。
2. **严禁越过人工确认直接调用计算**：底层 MCP 引擎装配了状态机安全守卫，未经人工显式确认场景与参数前，`execute_calculation` 工具将直接抛出拦截异常并拒绝执行。
3. **参数必须解释清楚**：向用户展示或询问参数时，必须附带物理量纲（单位）、工程释义及物理合理区间。

---

##  标准业务流程（状态机人机确认流程）

```
[初始态: 用户需求输入]
        │
        ▼
[1. AI 模式匹配 / 场景检索] ─── (无对应场景) ───► [1b. 新建或微调DAG管道]
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
- 若工况属于夜间低谷电蓄热、白天供蒸汽的典型工况，匹配系统内置基准管道：`scenario_electric_heater_salt_steam`。
- 先调用 `list_scenarios` 查看实际已注册的 Python 流水线目录，由 Agent 对照需求匹配，再将选定 ID 传给 `match_or_propose_scenario` 的 `scenario_id`。该工具不会自行完成需求匹配；所有会话工具始终使用同一工程的 `session_id`。
- **未匹配到合适场景时，必须新建场景或微调已有场景**，不得强行套用基准管道、跳过场景设计或由模型直接计算。按下文自扩展规范编写 Python `Pipeline`：已有场景仅局部不适用时，说明修改哪些参数、算子、求解方向和连接；现有拓扑不适用时组装新流水线。两种情况均需展示管道、获得人工审核，并重新进入场景确认流程。
- **Agent 行为规范**：调用该工具后，工具状态切换为 `SCENARIO_PROPOSED`，系统会自动在后台启动轻量可视化服务并在浏览器中呼出编辑器。Agent **必须停下来**，向用户输出：
  > “已为您匹配到计算场景：【电加热器熔盐储热供汽计算场景】。\n可视化编辑器已在浏览器打开: [编辑器链接]\n您可在图上按住鼠标空白拖动画布、自由拖拽移动卡片、点击算子进行前插/后插修改。请确认是否选用该场景并授权进入参数核对？”

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
  若返回 `is_complete=True`，状态切换为 `PARAMETERS_INSPECTED`，**Agent 必须调用 `open_pipeline_editor(session_id=当前工程会话ID, stage=2)`，主动将编辑器切换至【阶段 02: 运行参数填报态】**。阶段切换不代表参数已确认，也不授权计算。Agent **必须以 Markdown 表格形式**向用户汇报参数清单，并附带该工具返回的编辑器链接：
  > “所有计算参数已明确，清单如下：\n"
  > | 参数名称 | 变量标识 | 设定数值 | 工程单位 | 来源说明 |\n"
  > | :--- | :--- | :--- | :--- | :--- |\n"
  > | 蒸汽压力 | steam_pressure | 1.5 | MPa | 默认基准值 |\n"
  > ...\n"
  > 您也可以在浏览器可视化编辑器中直接微调图中数值；修改后只保存参数并使旧结果失效，不会即时重算。请确认参数无误并授权程序开始计算！”

### 第 4 步：人工确认参数 (Parameter Confirmation)
调用工具：`confirm_parameters(confirmed=True/False, feedback="...")`
- 用户确认无误后，调用 `confirm_parameters(confirmed=True)`；
- 状态机流转为 `PARAMETERS_CONFIRMED`，程序计算授权解锁！
- 用户微调参数后，Agent 必须重新调用 `inspect_and_validate_parameters`，展示最新参数表并等待用户确认，再调用 `confirm_parameters` 和 `execute_calculation`；不得沿用旧授权或因参数输入事件自动计算。

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

##  陌生场景与新公式自扩展规范 (Self-Extension Protocol)

当遇到《研究资料/使用场景/》中的新增场景（如“火电灵活性改造”、“热泵+中温熔盐”、“网侧独立储能”等）：

**沿用项目现有的 Python 公式与 Python Pipeline 写法。** 先阅读最相近的 `formulas/`、`pipelines/` 模块和对应包的 `__init__.py`，保留现有的元数据、引脚、注册表和状态机设计。新增或微调的场景仍须按前述六步流程人工确认，不因注册成功而获得计算授权。

### 1. 组合现有公式组装新管道
若现有原子公式库（查看 `list_formulas`）已覆盖所需节点，Agent 编写新的 `Pipeline` 脚本，声明 DAG 拓扑：
1. 向人类展示提议的管道结构与节点流向；
2. 获得人类审查同意后，将 Python 脚本保存到 `pipelines/<场景模块名>.py`，文件末尾调用 `pipeline_registry.register(...)`；在 `pipelines/__init__.py` 中增加对应模块的 `import pipelines.<场景模块名>`，使服务启动时加载并注册；
3. 在独立进程验证导入、流水线校验与渲染，再重启 MCP 服务，用 `list_scenarios` 确认场景已加载，随后按场景 ID 调用 `match_or_propose_scenario`，等待人工确认。

微调已有场景时，先向人类展示修改点。新增变体需使用独立的流水线 ID、模块名和实例名；若人类明确要求修改原场景，则修改原 Python 定义，重新加载服务后再次审核场景。参数默认值继续按现有场景从 `constants/default_parameters.py` 提取，新增参数可按现有 `Pin` 写法声明，不把缺失的工程假设当成已确认参数。

Python 流水线模板（以下节点引用下一节原有公式模板的 ID，实际使用时替换为已注册且适用的公式）：

```python
from core.pipeline import Pipeline, PipelineStep, pipeline_registry
from core.types import Pin

CUSTOM_REQUIRED_INPUTS = [
    Pin("var_a", "单位", "入参A详细说明", min_value=0.0, max_value=1000.0),
    Pin("var_b", "单位", "入参B详细说明", min_value=0.0, max_value=100.0),
]

CUSTOM_STEPS = [
    PipelineStep(
        step_id="step_1_custom_formula",
        formula_id="category.my_formula_name",
        input_map={"var_a": "var_a", "var_b": "var_b"},
        output_map={"var_c": "var_c"},
        description="使用已审核的公式计算出参C",
    ),
]

custom_pipeline = Pipeline(
    id="scenario_custom_scene",
    name="自定义场景名称",
    category="thermal",
    description="说明本场景的工艺过程、目标和适用范围",
    notes="说明工程假设、适用边界及待核对事项",
    required_inputs=CUSTOM_REQUIRED_INPUTS,
    steps=CUSTOM_STEPS,
)

pipeline_registry.register(custom_pipeline)
```

`input_map` 将公式已知引脚绑定到场景输入或其他步骤的产出，`output_map` 将待求引脚绑定到本步骤产出变量；引脚单位必须匹配。反算沿用 Python `PipelineStep(solve_target="待求变量", ...)`，已知引脚与输出映射随之调整。输入范围使用 `Pin` 声明，跨参数大小关系沿用 `InputConstraint`，熔盐专用约束参考现有场景的 `salt_temperature_constraints(...)`。含义和单位占位文字必须在实际工程中替换为经审核的定义。

在项目根目录用 `.venv/Scripts/python.exe run_web.py --pipeline pipelines/<场景模块名>.py` 打开该 Python 流水线进行渲染核对；也可使用已注册 ID。独立 Web 调试与 MCP 自带编辑器不应同时占用同一端口。文件导入和渲染不代替人工确认，也不授权执行计算。

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
向人类呈现该代码，人类确认数学正确与安全后，保存至 `formulas/<业务分类>/<公式模块名>.py`；保留末尾的 `default_formula_registry.register(my_new_formula)`。在 `formulas/__init__.py` 中增加对应导入，例如 `import formulas.thermal.<公式模块名>`，使服务启动时执行模块并注册公式。公式应先于引用它的流水线加载；现有 `pipelines/__init__.py` 已先导入 `formulas`。

若公式属于物性查表或离散选型，参照项目现有 `EmpiricalFormula` 的 Python 实现、校验函数和注册方式，不将其改写成不适用的代数关系。新增常量、设备规格或默认参数时，仍维护在现有 `constants/` 模块中。

### 3. MCP 注册工具与项目源码注册的区别

上述 Python 源文件、模块导入和注册表调用，是项目中新增公式、流水线的源码路径。服务已启动后修改文件，不会自动热加载；完成验证后重启，并分别用 `list_formulas`、`list_scenarios` 核对。

当前 MCP 也支持将上述受限 Python 模板作为字符串传给注册工具：
- `register_new_formula(formula_code=完整Python模板字符串, sub_category="thermal", filename="my_formula.py", human_approved=True)`；
- `register_new_pipeline(pipeline_code=完整Python模板字符串, pipeline_filename="custom_scene.py", human_approved=True)`。

只有获得人类对该公式或流水线的明确审核同意，才可传 `human_approved=True`。模板解析器允许白名单导入、赋值、`Pin`、`FormulaMetadata`、`AlgebraicFormula`、`PipelineStep`、`Pipeline`、`InputConstraint` 构造及一次指定注册表的注册声明；不执行任意 Python 代码，不能用该接口提交函数定义、循环或读取常量模块的辅助函数。带 `_get_pin` 等辅助函数的完整项目模块应走源码路径。

**当前工具不会把模板写入 `formulas/` 或 `pipelines/` 的 `.py` 源文件**：它解析 Python 模板后进行校验、持久化到服务数据目录并即时注册，重启时恢复。`filename` 和 `pipeline_filename` 只是被校验的参数，不是源码输出路径。不要把工具返回 `SUCCESS` 当作源码已生成。为使新增能力属于项目 Python 源码，应使用前述源码路径；同一流水线 ID 不要同时经源码与工具重复注册。

### 4. AI 阶段控制与前端调试

正常模式由 Agent 调用 `open_pipeline_editor(session_id=当前工程会话ID, stage=1或2)` 控制展示阶段，已打开的同会话页面会同步命令；前端阶段按钮和确认计算按钮仅供调试。阶段 02 必须先完成场景的人工确认，阶段切换本身不执行计算，也不替代参数审核。

独立调试时使用 `.venv/Scripts/python.exe run_web.py --debug --pipeline <Python流水线文件或ID>`，启用前端阶段切换及确认计算按钮。`--stage 2` 仅与 `--debug` 一起使用；未传 `--debug` 时按 AI 控制模式运行，不能通过浏览器地址参数启用调试。即使处于调试模式，修改参数也只保存并撤销旧计算授权，须显式确认后计算。
