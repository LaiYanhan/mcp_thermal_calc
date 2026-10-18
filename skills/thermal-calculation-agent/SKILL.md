---
name: thermal-calculation-agent
description: 熔盐储能与工业热工计算智能体技能规范。严格执行状态机硬性中断流程，协调物理选型、热平衡与经济性测算，严禁模型自行心算任何数值。
---

# 熔盐储能与热工测算智能体指南

本技能指导 Agent 作为热工工程测算顾问，严格执行下述状态机与人工确认流程，调用项目 JSON 原子公式、计算管道和 MCP 工具完成测算。

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
- 先调用 `list_scenarios` 查看实际已注册的 JSON 计算管道目录，由 Agent 对照需求匹配，再将选定 ID 传给 `match_or_propose_scenario` 的 `scenario_id`。该工具不会自行完成需求匹配；所有会话工具始终使用同一工程的 `session_id`。
- **未匹配到合适场景时，必须新建场景或微调已有场景**，不得强行套用基准管道、跳过场景设计或由模型直接计算。按下文自扩展规范编写自包含 JSON 计算管道：已有场景仅局部不适用时，说明修改哪些参数、算子、求解方向和连接；现有拓扑不适用时组装新流水线。两种情况均需展示管道、获得人工审核，并重新进入场景确认流程。
- **Agent 行为规范**：调用该工具后，工具状态切换为 `SCENARIO_PROPOSED`，系统会自动在后台启动轻量可视化服务并在浏览器中呼出编辑器。Agent **必须停下来**，向用户输出：
  > “已为您匹配到计算场景：【电加热器熔盐储热供汽计算场景】。\n可视化编辑器已在浏览器打开: [编辑器链接]\n您可在图上按住鼠标空白拖动画布、自由拖拽移动卡片、点击算子进行前插/后插修改。请确认是否选用该场景并授权进入参数核对？”

### 第 2 步：人工确认场景 (Scenario Confirmation)
调用工具：`confirm_scenario(confirmed=True/False, feedback="...")`
- 当用户明确表示“同意”、“确认”、“可以”时，调用 `confirm_scenario(confirmed=True)`，进入参数检查阶段；
- 若用户提出异议（如“我们是不带储热的电锅炉方案”或“需要用太阳盐”），调用 `confirm_scenario(confirmed=False, feedback=用户意见)`，调整场景后再征求确认。

### 第 3 步：参数检查与缺项询问 (Parameter Inspection)
调用工具：`inspect_and_validate_parameters`
- 传入用户已提供的参数字典。工具检查缺项并补全当前管道 JSON 内联的默认值，默认值仍需人工核对。
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

完整 JSON 定义与注册示例见 [JSON 定义与注册示例](references/json-definitions.md)；该参考补充下述扩展规则，不替代上述详细业务流程与注意事项。

当遇到《研究资料/使用场景/》中的新增场景（如“火电灵活性改造”、“热泵+中温熔盐”、“网侧独立储能”等）：

先用 `list_formulas`、`list_scenarios` 阅读完整 `definition`，复用最相近的已注册资产。公式和管道统一使用严格 JSON，定义的字段与类型以注册工具 schema 为准。新场景或微调仍须执行前述人工确认流程。

### 1. 组合现有公式组装新管道

向人类展示节点、变量来源、求解方向及工程假设。管道 JSON 在 `required_inputs` 中内联每个输入和工程常量的 `name`、`unit`、`description`、`default_value`，用 `kind="constant"` 标明常量；缺少工程依据的量保留为无默认值的必填项。在 `steps` 中声明 `step_id`、`formula_id`、`input_map` 和 `output_map`，来源必须是场景输入或其他步骤输出，单位须匹配。

反算节点使用 `solve_target="待求变量"`，其余公式变量作为已知量映射到 `input_map`，待求量映射到 `output_map`；省略时使用默认方向。`list_formulas` 的 `solve_targets` 给出可选变量；物性和选型保持正向。

新增变体采用独立 ID；微调原场景须先展示修改点并取得对应授权。审核后调用 `register_new_pipeline(pipeline_definition=JSON对象, pipeline_filename="scenario_id.json", human_approved=True)`，写入 `pipelines/` 并即时注册。也可将审核后的 JSON 文件放入该目录，重启服务自动发现。用 `list_scenarios` 核对，再提议场景并等待会话中的人工确认。

微调已有场景时，先向人类展示修改点。若人类明确要求修改原场景，则修改原 JSON 定义，重新加载服务后再次审核场景。不把缺失的工程假设当成已确认参数。

在独立进程验证 JSON 加载、流水线校验与渲染，再重启 MCP 服务，用 `list_scenarios` 确认场景已加载，随后按场景 ID 调用 `match_or_propose_scenario`，等待人工确认。含义和单位占位文字必须在实际工程中替换为经审核的定义。

在项目根目录用 `.venv/Scripts/python.exe run_web.py --pipeline pipelines/<场景标识>.json` 打开该 JSON 流水线进行渲染核对；也可使用已注册 ID。独立 Web 调试与 MCP 自带编辑器不应同时占用同一端口。文件导入和渲染不代替人工确认，也不授权执行计算。

### 2. 新原子公式

代数公式 JSON 声明 `id`、`name`、`category`、`formula_type="algebraic"`、`expression`、`inputs`、`outputs`。每个引脚明确变量、中文含义及单位；数学表达式使用英文变量标识及 `+ - * / **`，正向输出须有唯一解析解。公式表达通用物理、选型或经济关系，与具体业务场景解耦。

物性和离散选型公式使用 `formula_type="empirical"`、已注册 `handler` 和对应引脚，`is_bidirectional=false`。handler 实现固定在核心白名单中；需要新物性算法时，应先作为代码开发任务实现和验证处理函数，再声明 JSON，不能通过 JSON 动态导入函数。

若公式属于物性查表或离散选型，不将其改写成不适用的代数关系。

向工程师展示公式及工程含义，明确审核通过后调用 `register_new_formula(formula_definition=JSON对象, filename="中文计算含义_english_id.json", human_approved=True)`。工具校验后写入 `formulas/` 并注册；手工添加文件则需重启。公式先于引用它的管道加载；不需要修改包导入或注册代码。

### 3. 数值与持久化边界

`min_value`、`max_value` 是显示参考范围，旧 `input_constraints` 只保留元数据，不阻断探索性输入。说明范围供工程师判断，不宣称工具已完成物理合理性审查。有限数值可进入计算；除零、非有限结果和底层 IAPWS-95 无法求解的状态仍会报错。报告实际工具错误，不替换或猜测结果。

默认值在管道内联，运行时不从 Python 常量模块补查。注册资产直接保存为项目 JSON；会话草稿和布局另存于数据目录。历史 `.data/` 资产本次不自动迁移。注册不会授予计算权限，重启也不恢复旧授权。

只有获得人类对该公式或流水线的明确审核同意，才可传 `human_approved=True`。同一流水线 ID 不要同时经手工 JSON 文件与工具重复注册。

### 4. AI 阶段控制与前端调试

正常模式由 Agent 调用 `open_pipeline_editor(session_id=当前工程会话ID, stage=1或2)` 控制展示阶段，已打开的同会话页面会同步命令；前端阶段按钮和确认计算按钮仅供调试。阶段 02 必须先完成场景的人工确认，阶段切换本身不执行计算，也不替代参数审核。

独立调试时使用 `.venv/Scripts/python.exe run_web.py --debug --pipeline <JSON流水线文件或ID>`，启用前端阶段切换及确认计算按钮。`--stage 2` 仅与 `--debug` 一起使用；未传 `--debug` 时按 AI 控制模式运行，不能通过浏览器地址参数启用调试。即使处于调试模式，修改参数也只保存并撤销旧计算授权，须显式确认后计算。
