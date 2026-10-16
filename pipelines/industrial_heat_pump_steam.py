"""
工业热泵储能供汽计算流水线 (Industrial Heat Pump with Thermal Storage Steam Supply Pipeline)

场景标识: scenario_industrial_heat_pump_steam
场景名称: 工业热泵储能供汽计算场景
所属分类: heat_pump_steam

【说明】
本文件为工业热泵储热供汽场景的空白骨架与初始化模板。
您可以在此基础上自主添加/微调输入参数与拓扑算子序列。
"""

from constants.default_parameters import DEFAULT_VALLEY_SALT_STEAM_PARAMS
from core.pipeline import Pipeline, PipelineStep, pipeline_registry
from core.types import Pin


def _get_pin(key: str) -> Pin:
    """辅助函数：从集中基准参数字典快速提取引脚定义；亦可直接通过 Pin(...) 自行定义"""
    if key in DEFAULT_VALLEY_SALT_STEAM_PARAMS:
        cfg = DEFAULT_VALLEY_SALT_STEAM_PARAMS[key]
        return Pin(
            name=key,
            unit=cfg["unit"],
            description=cfg["description"],
            min_value=cfg.get("min_value"),
            max_value=cfg.get("max_value"),
            default_value=cfg.get("value"),
            kind="input",
        )
    return Pin(name=key, unit="/", description=key, kind="input")


# ==============================================================================
# 1. 声明该管道必需的所有工况输入参数与工程常量 (HEAT_PUMP_STEAM_REQUIRED_INPUTS)
# ==============================================================================
HEAT_PUMP_STEAM_REQUIRED_INPUTS = [
    # --- 基础水/蒸汽工况输入 ---
    _get_pin("steam_pressure"),              # 蒸汽绝对工作压力 (MPa)
    _get_pin("steam_temperature"),           # 蒸汽供汽温度 (℃)
    _get_pin("feedwater_pressure"),          # 给水绝对压力 (MPa)
    _get_pin("feedwater_temperature"),       # 给水水温 (℃)
    _get_pin("steam_mass_flow"),             # 额定蒸汽流量 (t/h)

    # --- 生产周期与运行参数 ---
    _get_pin("steam_supply_hours"),          # 每日供汽时长 (h)
    _get_pin("valley_electricity_hours"),    # 每日低谷电时长 (h)
    _get_pin("annual_operating_days"),       # 年有效运行天数 (d)

    # --- 核心热泵与储能常量 ---
    Pin(
        name="heat_pump_cop",
        unit="/",
        description="高温工业热泵制热性能系数 COP",
        default_value=1.30,
        min_value=1.05,
        max_value=4.50,
        kind="constant",
    ),
    Pin(
        name="thermal_storage_efficiency",
        unit="/",
        description="储热罐保温与储热效率",
        default_value=0.99,
        min_value=0.80,
        max_value=1.00,
        kind="constant",
    ),

    # TODO: [待您自主扩展] 可在此处追加更多自定义输入/常量参数，例如：
    # Pin(name="valley_electricity_price", unit="元/kWh", description="低谷电价", default_value=0.30, kind="input"),
    # Pin(name="steam_market_price", unit="元/t", description="蒸汽市售价格", default_value=180.0, kind="input"),
]


# ==============================================================================
# 2. 声明有向无环图 (DAG) 拓扑连接步骤序列 (HEAT_PUMP_STEAM_STEPS)
# ==============================================================================
HEAT_PUMP_STEAM_STEPS = [
    # 步骤 1: 查表确定蒸汽比焓
    PipelineStep(
        step_id="step_1_steam_enthalpy",
        formula_id="thermal.steam_enthalpy",
        input_map={"steam_pressure": "steam_pressure", "steam_temperature": "steam_temperature"},
        output_map={"steam_enthalpy": "steam_enthalpy"},
        description="根据蒸汽压力和温度，基于 IAPWS-95 查表计算蒸汽比焓",
    ),
    # 步骤 2: 查表确定给水比焓
    PipelineStep(
        step_id="step_2_water_enthalpy",
        formula_id="thermal.water_enthalpy",
        input_map={"feedwater_pressure": "feedwater_pressure", "feedwater_temperature": "feedwater_temperature"},
        output_map={"feedwater_enthalpy": "feedwater_enthalpy"},
        description="根据给水压力和温度，基于 IAPWS-95 查表计算给水比焓",
    ),
    # 步骤 3: 计算有效换热焓差
    PipelineStep(
        step_id="step_3_enthalpy_diff",
        formula_id="thermal.enthalpy_diff",
        input_map={"steam_enthalpy": "steam_enthalpy", "feedwater_enthalpy": "feedwater_enthalpy"},
        output_map={"enthalpy_diff": "enthalpy_diff"},
        description="计算水相变为目标参数蒸汽所需的有效比焓增量（焓差）",
    ),

    # TODO: [待您自主搭建] 请在此处依次装配后续热泵制热与储能算子：
    # 步骤 4: 理论产汽功率 / SGS换热功率
    # 步骤 5: 供汽期总吸热量（制热量）
    # 步骤 6: 热泵额定制热热功率
    # 步骤 7: 热泵额定输入电功率（基于 COP 折算）
    # 步骤 8: 储热系统额定储热容量
    # 步骤 9: 年累计用电量与年累计供汽量...
]


# ==============================================================================
# 3. 管道实例化与自动注册 (Pipeline Instance & Registration)
# ==============================================================================
industrial_heat_pump_steam_pipeline = Pipeline(
    id="scenario_industrial_heat_pump_steam",
    name="工业热泵储能供汽计算场景",
    category="heat_pump_steam",
    description=(
        "该项目为工业高温热泵结合储能供蒸汽计算场景。利用低谷电价时段启动工业热泵，"
        "以高制热性能系数 (COP) 高效制热并储存于储热系统中；在白天生产用热时段通过 SGS 连续供应工业蒸汽。"
        "实现源侧/用户侧削峰填谷、大幅降低耗电量与运行成本。"
    ),
    notes=(
        "1. 基础热工比焓与有效焓差框架已初始化就绪；\n"
        "2. 详细热泵制热转换、COP 折算及运行经济性步骤待用户根据工程实际搭建装配。"
    ),
    required_inputs=HEAT_PUMP_STEAM_REQUIRED_INPUTS,
    steps=HEAT_PUMP_STEAM_STEPS,
)

# 自动注册进管道全局注册表
pipeline_registry.register(industrial_heat_pump_steam_pipeline)
