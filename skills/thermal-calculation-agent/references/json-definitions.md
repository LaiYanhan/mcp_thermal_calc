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

已有通用 handler 可复用为经验公式；例如文件 `SGS功率整定_doc_sgs_sizing.json`：

```json
{
  "id": "custom.doc_sgs_sizing",
  "name": "SGS功率规格整定",
  "category": "sizing",
  "formula_type": "empirical",
  "handler": "data.fixed_step",
  "is_bidirectional": false,
  "inputs": [
    {"name": "value", "unit": "MW", "description": "需求功率"}
  ],
  "outputs": [
    {"name": "result", "unit": "MW", "description": "规格功率"}
  ],
  "data_inputs": [{"name": "table", "rule_type": "fixed_step", "input_unit": "MW", "output_unit": "MW"}]
}
```

通用数据 handler 使用 `value` / `result` 数值引脚，单位由 JSON 数据端口声明并与所绑定表核对；IAPWS95 handler 仍使用自身固定引脚及单位。上述例子还须在场景中声明正数 `step`、整定方式及 `data_map` 绑定，完整形式见下文。经验公式保持正向，不设置反算 `solve_target`，不填写代数 `expression`。

## 场景内工程数据与通用取值

参数与单值常量继续内联于 `required_inputs`，不需要公共常量库注册。成组数据放在当前管道的 `data_tables`；数据端口不属于数值引脚，不能将整表接到 `input_map`。核心支持以下规则，业务名称、单位、步长和表值由 JSON 定义：

| handler / rule_type | 数据字段 | 取值规则 |
| --- | --- | --- |
| `data.fixed_step` / `fixed_step` | 正数 `step`、`mode` | 以零为基准的固定步长整定 |
| `data.discrete` / `discrete` | 严格递增且非空的 `levels`、`mode` | 从不等距档位中取值 |
| `data.piecewise` / `piecewise` | 严格按 `threshold` 递增的非空 `rows` | 每行含 `threshold` 与 `value`，左闭右开；等于阈值进入该行所在的新段 |
| `data.correlation` / `correlation` | 非空 `terms` 与非零 `divisor` | 每项含有限 `coefficient` 与 `power`；取各项幂次乘积之和再除以 `divisor`，省略除数使用数学恒等值 1 |

`mode` 为 `ceil`（向上）、`floor`（向下）或 `nearest`（最近）。最近整定在中点采用半入规则：2.5 取 3，-2.5 取 -3；不等距档位距离相同时选绝对值较大者。离散档位和分段查表低于或高于输入范围时取首行或末行对应结果，不增加表外警告；分段输出可以非单调，首末按阈值顺序确定。固定步长没有表的首末边界。分段取值返回一个值，不进行分段累进、插值或反算。

四种通用 handler 均使用数值输入 `value`、输出 `result` 及数据端口 `table`。公式 `data_inputs` 的 `rule_type` 须与 handler 及所绑定的表一致，`input_unit` / `output_unit` 须分别匹配数值输入、输出引脚。整定的输入输出单位必须相同量纲、相同倍率；分段查表与关联式可以使用不同的输入输出单位。

例如先审核并注册公式 `通用刻度整定_doc_quantization.json`：

```json
{
  "id": "custom.doc_quantization",
  "name": "通用刻度整定",
  "category": "custom",
  "formula_type": "empirical",
  "handler": "data.fixed_step",
  "inputs": [{"name": "value", "description": "需求值", "unit": "kW"}],
  "outputs": [{"name": "result", "description": "整定值", "unit": "kW"}],
  "data_inputs": [{"name": "table", "rule_type": "fixed_step", "input_unit": "kW", "output_unit": "kW"}]
}
```

再审核并注册 `scenario_doc_quantization.json`，或通过原有 `new_scenario_def` 仅向当前会话提议：

```json
{
  "id": "scenario_doc_quantization",
  "name": "中性整定示例",
  "required_inputs": [{"name": "requested", "description": "待确认需求", "unit": "kW"}],
  "data_tables": [{
    "id": "local_scale",
    "description": "本场景刻度",
    "input_unit": "kW",
    "output_unit": "kW",
    "rule_type": "fixed_step",
    "step": 1,
    "mode": "nearest"
  }],
  "steps": [{
    "step_id": "quantize",
    "formula_id": "custom.doc_quantization",
    "input_map": {"value": "requested"},
    "output_map": {"result": "quantized"},
    "data_map": {"table": "local_scale"}
  }]
}
```

离散档位使用 `rule_type="discrete"`、例如 `levels=[1, 4, 9]` 和所需 `mode`；同时将公式 handler 改为 `data.discrete`、数据端口规则改为 `discrete`。分段数据使用 `rule_type="piecewise"` 和例如 `rows=[{"threshold": 0, "value": 40}, {"threshold": 10, "value": 90}, {"threshold": 20, "value": 15}]`，公式对应 `data.piecewise` 与 `piecewise` 数据端口，不填写 `mode`。新增这些同类表不需要新增 Python handler；全新算法仍可开发新的白名单处理函数。

不使用数据端口的 JSON 可以省略 `data_inputs`、`data_tables` 与 `data_map`，按空声明兼容。旧设备专用 handler 已删除；四个设备公式 ID 保留，数值引脚改为 `value` / `result`，旧自定义场景须同步调整映射并添加表绑定后重新确认。表内容、绑定随保存、启动加载、目录和会话快照保留；其他场景的数据不会替换当前快照。手工改磁盘 JSON 后需重启，不自动热加载。通过原有会话接口修改表后必须重新确认；注册与提议不会授予正式计算权限，预览仍不保存正式成果。前端既有保存操作会保留表，本轮不提供整表编辑器；表计算只通过管道节点执行。

## 已迁移工程资料

`constants/default_parameters.json` 保存原有 18 项基准参数的完整值和元数据；实际场景继续读取自身 `required_inputs`。`constants/equipment_catalog.json` 保存三种整定刻度、13 档变压器容量、三张阶梯造价表、两种方案功率因数和电气单位造价。`constants/molten_salt.json` 保存两种熔盐的组分、别名、温度资料及八个物性关联式表；其 `profiles[].formulas` 指向已有原子公式 ID。

复用资料时，读取 JSON，将所需参数转换为场景 `required_inputs`（`value` 写为 `default_value`，单值常量标为 `kind="constant"`），所需表完整复制到 `data_tables`，再在节点中引用其 ID。不依赖 Python 常量模块，不要求公共登记，也不让资料文件的后续修改覆盖已有场景快照。资料保留原始温区与关联式，不表示重新验证了物性模型。

关联式表的 `terms` 每项保存 `coefficient` 和 `power`，由 `data.correlation` 计算 `sum(coefficient * value ** power) / divisor`。幂次可以为负数或非整数；除零、负底数的非实数幂及非有限结果沿用实际计算错误，不增加替代模型或温区拦截。温度等输入单位由端口契约明确，不隐式换算。

变压器档位表使用 MVA；有功功率 MW 先接入 `electrical.apparent_capacity`，将场景中声明的功率因数连接到 `power_factor`，再把产出的 MVA 接到 `sizing.transformer_sizing` 的 `value`。超过最高档位沿用通用首末边界，不再隐式按最大档位倍数组合；需要多台组合时另行明确建模。

## 反算、文件与校验

代数公式的 `inputs` / `outputs` 表示默认方向。节点反算时，从目录 `solve_targets` 选择待求量，`input_map` 绑定其余全部变量，`output_map` 只绑定本次实际输出；同时调整外部输入及下游来源，避免重复生产变量或循环。

公式 ID 可含字母、数字、下划线和点，且以英文字母开头；管道及步骤 ID 还可含连字符。引脚与产出变量使用英文标识，单位需同量纲同倍率；不同倍率先显式换算。未知字段、重复 ID、重复引脚、错误 handler 契约、缺失来源与循环会被拒绝。

注册文件名必须为单个 `.json` 文件名，不包含目录；使用有物理含义的中文加英文标识。`layout` 的每个位置提供有限数值 `left` 和 `top`。范围元数据仅供提示，不能据此声称工况已通过物理合理性审查。

手工文件位于资产根目录下的 `formulas/`、`pipelines/`，服务启动时递归发现。手工更新已注册 JSON 后重启服务再核对目录；同一 ID 的多个文件会阻止加载，不通过改名复制文件来覆盖已有定义。全部步骤的实际输出自动成为成果，无须 `output_groups` 等旧分组字段。
