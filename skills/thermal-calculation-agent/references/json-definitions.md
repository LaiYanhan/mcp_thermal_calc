# JSON 定义与注册示例

用于新增原子公式或计算管道。以下定义是独立示例，不表示某个工程的参数已经确定；两个输入均未设置默认值，执行前需由工程师提供并确认。

## 通用代数公式

公式文件名为 `理论产汽功率_doc_theoretical_power.json`，传入 `register_new_formula` 的 `formula_definition`：

```json
{
  "id": "custom.doc_theoretical_power",
  "name": "理论产汽功率计算",
  "category": "thermal",
  "formula_type": "algebraic",
  "expression": "power = mass_flow * enthalpy_diff / 3600",
  "description": "由质量流量和比焓差换算热功率",
  "inputs": [
    {"name": "mass_flow", "unit": "t/h", "description": "质量流量"},
    {"name": "enthalpy_diff", "unit": "kJ/kg", "description": "比焓差"}
  ],
  "outputs": [
    {"name": "power", "unit": "MW", "description": "热功率"}
  ]
}
```

审核后调用 `register_new_formula(formula_definition=上述JSON对象, filename="理论产汽功率_doc_theoretical_power.json", human_approved=True)`。传结构化对象，使用 `expression` 字段；旧 `formula_code`、`sub_category` 和 Python 模板均不是当前 MCP 接口。前端 `/api/operator/add` 保留 `equation` 载荷，由后端适配为同一标准资产。

## 自包含管道

先注册上面的公式，再将以下对象传入 `register_new_pipeline` 的 `pipeline_definition`，文件名为 `scenario_doc_power.json`：

```json
{
  "id": "scenario_doc_power",
  "name": "流量焓差换算热功率",
  "category": "thermal",
  "description": "演示自包含输入及节点变量映射",
  "required_inputs": [
    {"name": "flow", "unit": "t/h", "description": "质量流量", "kind": "input"},
    {"name": "delta_h", "unit": "kJ/kg", "description": "比焓差", "kind": "input"}
  ],
  "steps": [
    {
      "step_id": "power_from_flow",
      "formula_id": "custom.doc_theoretical_power",
      "solve_target": "power",
      "input_map": {"mass_flow": "flow", "enthalpy_diff": "delta_h"},
      "output_map": {"power": "required_power"}
    }
  ],
  "layout": {},
  "input_constraints": []
}
```

审核后调用 `register_new_pipeline(pipeline_definition=上述JSON对象, pipeline_filename="scenario_doc_power.json", human_approved=True)`。`required_inputs` 内联所有外部量与常量的名称、单位和含义；确定的基准值写入 `default_value`，常量标为 `kind="constant"`。没有默认值的量为必填，不能在注册或提议时假定已得到确认。

注册后用 `list_scenarios` 核对，再以该 ID 提议场景。仅用于当前会话时，也可直接通过 `match_or_propose_scenario(new_scenario_def=上述JSON对象, ...)` 提议；此方式不将管道保存为全局 JSON 资产。

## 已注册经验 handler

已有 handler 可复用为经验公式；例如文件 `SGS功率整定_doc_sgs_sizing.json`：

```json
{
  "id": "custom.doc_sgs_sizing",
  "name": "SGS功率规格整定",
  "category": "sizing",
  "formula_type": "empirical",
  "handler": "sizing.sgs_power",
  "is_bidirectional": false,
  "inputs": [
    {"name": "sgs_power", "unit": "MW", "description": "需求功率"}
  ],
  "outputs": [
    {"name": "sgs_sizing_mw", "unit": "MW", "description": "规格功率"}
  ]
}
```

handler 的引脚名称与单位由核心契约决定，不能仅更改 JSON 名称或倍率使其计算另一种量；可在管道映射中改用不同来源变量。经验公式保持正向，不设置反算 `solve_target`，不填写代数 `expression`。

## 反算、文件与校验

代数公式的 `inputs` / `outputs` 表示默认方向。节点反算时，从目录 `solve_targets` 选择待求量，`input_map` 绑定其余全部变量，`output_map` 只绑定本次实际输出；同时调整外部输入及下游来源，避免重复生产变量或循环。

公式 ID 可含字母、数字、下划线和点，且以英文字母开头；管道及步骤 ID 还可含连字符。引脚与产出变量使用英文标识，单位需同量纲同倍率；不同倍率先显式换算。未知字段、重复 ID、重复引脚、错误 handler 契约、缺失来源与循环会被拒绝。

注册文件名必须为单个 `.json` 文件名，不包含目录；使用有物理含义的中文加英文标识。`layout` 的每个位置提供有限数值 `left` 和 `top`。范围元数据仅供提示，不能据此声称工况已通过物理合理性审查。

手工文件位于资产根目录下的 `formulas/`、`pipelines/`，服务启动时递归发现。手工更新已注册 JSON 后重启服务再核对目录；同一 ID 的多个文件会阻止加载，不通过改名复制文件来覆盖已有定义。全部步骤的实际输出自动成为成果，无须 `output_groups` 等旧分组字段。
