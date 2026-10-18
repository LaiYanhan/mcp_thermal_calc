"""
工业热泵储能供汽计算流水线 (Industrial Heat Pump with Thermal Storage Steam Supply Pipeline)

场景标识: scenario_industrial_heat_pump_steam
场景名称: 工业热泵熔盐储能供汽计算场景
所属分类: heat_pump_steam

"""

from constants.default_parameters import DEFAULT_VALLEY_SALT_STEAM_PARAMS
from core.pipeline import Pipeline, PipelineStep, pipeline_registry
from core.types import Pin
from pipelines.validation import salt_temperature_constraints


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
            kind="constant" if key in ("electric_heater_efficiency", "heat_exchanger_efficiency", "thermal_storage_efficiency", "salt_specific_heat", "salt_safety_margin", "heat_pump_cop") else "input",
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

    # --- 工程常量参数 ---
    _get_pin("heat_pump_cop"),               # 高温工业热泵制热性能系数 COP
    _get_pin("heat_exchanger_efficiency"),   # SGS换热器换热综合效率 (工程常量，默认 0.99)
    _get_pin("thermal_storage_efficiency"),  # 熔盐储热罐保温与储热效率 (工程常量，默认 0.99)

    # --- 熔盐储热参数 ---
    _get_pin("salt_hot_temperature"),
    _get_pin("salt_cold_temperature"),
    _get_pin("salt_specific_heat"),
    _get_pin("salt_safety_margin"),

    # --- 运行经济参数 ---
    _get_pin("valley_electricity_price"),
    _get_pin("steam_market_price"),
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
    # 步骤 4: 计算理论产汽功率
    PipelineStep(
        step_id="step_4_theoretical_power",
        formula_id="thermal.theoretical_power",
        input_map={"steam_mass_flow": "steam_mass_flow", "enthalpy_diff": "enthalpy_diff"},
        output_map={"theoretical_power": "theoretical_power"},
        description="根据额定蒸汽流量与进出口焓差，计算产生蒸汽所需的理论净吸热功率（MWt）",
    ),
    # 步骤 5: 计算 SGS 实际换热功率
    PipelineStep(
        step_id="step_5_sgs_power",
        formula_id="thermal.sgs_power",
        input_map={"theoretical_power": "theoretical_power", "heat_exchanger_efficiency": "heat_exchanger_efficiency"},
        output_map={"sgs_power": "sgs_power"},
        description="计入换热损失后，折算SGS换热器侧实际需要的换热热功率（MWt）",
    ),
    # 步骤 6: 供汽期总吸热量（功率转能量）
    PipelineStep(
        step_id="step_6_steam_heat_supply",
        formula_id="thermal.steam_heat_supply",
        input_map={
            "sgs_power": "sgs_power",
            "steam_supply_hours": "steam_supply_hours",
        },
        output_map={"steam_heat_supply": "steam_heat_supply"},
        description="结合供汽时长，将SGS换热功率转换为供汽周期累计释放的总热能（MWh）",
    ),
    # 步骤 7: 计算储热罐额定储热容量
    PipelineStep(
        step_id="step_7_thermal_storage_capacity",
        formula_id="thermal.thermal_storage_capacity",
        input_map={
            "steam_heat_supply": "steam_heat_supply",
            "thermal_storage_efficiency": "thermal_storage_efficiency",
        },
        output_map={"thermal_storage_capacity": "thermal_storage_capacity"},
        description="计入储罐保温与散热损失，计算储热系统额定储热容量（MWht）",
    ),
    # 步骤 8: 计算热泵制热输出电功率 
    PipelineStep(
        step_id="step_8_heat_pump_power",
        formula_id="thermal.heat_pump_thermal_power",
        input_map={
            "thermal_storage_capacity": "thermal_storage_capacity",
            "valley_electricity_hours": "valley_electricity_hours",
        },
        output_map={"heat_pump_thermal_power": "heat_pump_thermal_power"},
        description="根据总热容量与每日低谷电时长，计算热泵在低谷电时段的制热输出功率（MWt）",
    ),
    # 步骤 9: 计算热泵输入电功率
    PipelineStep(
        step_id="step_9_heat_pump_electric_power",
        formula_id="thermal.heat_pump_electric_power",
        input_map={
            "heat_pump_thermal_power": "heat_pump_thermal_power",
            "heat_pump_cop": "heat_pump_cop",
        },
        output_map={"heat_pump_electric_power": "heat_pump_electric_power"},
        description="根据热泵制热输出功率与制热性能系数 COP，计算热泵在低谷电时段的输入电功率（MWe）",
    ),  
    # 步骤 10: 计算每日消纳谷电用电量
    PipelineStep(
        step_id="step_10_heat_pump_daily_electricity",
        formula_id="operation.heat_pump_daily_electricity",
        input_map={
            "heat_pump_electric_power": "heat_pump_electric_power",
            "valley_electricity_hours": "valley_electricity_hours",
        },
        output_map={"daily_power_mwh": "daily_power_mwh"},
        description="计算每日消纳低谷电用电量（MWh/d）",
    ),
    # 步骤 11: 计算熔盐需求量
    PipelineStep(
        step_id="step_11_molten_salt_mass",
        formula_id="thermal.molten_salt_mass",
        input_map={
            "thermal_storage_capacity": "thermal_storage_capacity",
            "salt_specific_heat": "salt_specific_heat",
            "salt_hot_temperature": "salt_hot_temperature",
            "salt_cold_temperature": "salt_cold_temperature",
            "salt_safety_margin": "salt_safety_margin",
        },
        output_map={"salt_mass": "salt_mass"},
        description="根据储热容量、熔盐高低温差、定压比热容及安全冗余系数确定理论熔盐净重",
    ),
    # 步骤 12: 熔盐采购量工程整定
    PipelineStep(
        step_id="step_12_salt_mass_roundup",
        formula_id="sizing.salt_mass_roundup",
        input_map={"salt_mass": "salt_mass"},
        output_map={"salt_mass_tons": "salt_mass_tons"},
        description="理论熔盐净重向上圆整至整 10 吨采购订货量",
    ),
    # 步骤 13: 年累计消纳电量计算
    PipelineStep(
        step_id="step_13_annual_electricity",
        formula_id="operation.annual_electricity",
        input_map={
            "daily_power_mwh": "daily_power_mwh",
            "annual_operating_days": "annual_operating_days",
        },
        output_map={"annual_power_wan_kwh": "annual_power_wan_kwh"},
        description="按年有效运营天数测算年累计用电量（万kWh/年）",
    ),
    # 步骤 14: 每日供汽总量计算
    PipelineStep(
        step_id="step_14_daily_steam_production",
        formula_id="operation.daily_steam_production",
        input_map={
            "steam_mass_flow": "steam_mass_flow",
            "steam_supply_hours": "steam_supply_hours",
        },
        output_map={"daily_steam_tons": "daily_steam_tons"},
        description="计算每日累计外供蒸汽吨数（t/d）",
    ),
    # 步骤 15: 年累计供汽量计算
    PipelineStep(
        step_id="step_15_annual_steam_production",
        formula_id="operation.annual_steam_production",
        input_map={
            "daily_steam_tons": "daily_steam_tons",
            "annual_operating_days": "annual_operating_days",
        },
        output_map={"annual_steam_wan_tons": "annual_steam_wan_tons"},
        description="测算年累计外供蒸汽量（万t/年）",
    ),
    # 步骤 16: 每日购电成本计算
    PipelineStep(
        step_id="step_16_daily_electricity_cost",
        formula_id="operation.daily_electricity_cost",
        input_map={
            "daily_power_mwh": "daily_power_mwh",
            "valley_electricity_price": "valley_electricity_price",
        },
        output_map={"daily_electricity_cost": "daily_electricity_cost"},
        description="计算每日谷电购电费用支出（元/d）",
    ),
    # 步骤 17: 每日售汽收入计算
    PipelineStep(
        step_id="step_17_daily_steam_revenue",
        formula_id="operation.daily_steam_revenue",
        input_map={
            "daily_steam_tons": "daily_steam_tons",
            "steam_market_price": "steam_market_price",
        },
        output_map={"daily_steam_revenue": "daily_steam_revenue"},
        description="计算每日外供蒸汽营业收入（元/d）",
    ),
    # 步骤 18: 每日经营毛收益差额计算
    PipelineStep(
        step_id="step_18_daily_operating_spread",
        formula_id="operation.daily_operating_spread",
        input_map={
            "daily_steam_revenue": "daily_steam_revenue",
            "daily_electricity_cost": "daily_electricity_cost",
        },
        output_map={"daily_operating_spread": "daily_operating_spread"},
        description="计算日度售汽收入与低谷购电成本的毛利差额（元/d）",
    ),
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
        "1. 已包含比焓、供热量、COP 折算、电耗、选型及运行经济性计算；\n"
        "2. COP 为给定工况假设，未建立热源侧与温升性能模型，需依据实际设备性能核对。"
    ),
    required_inputs=HEAT_PUMP_STEAM_REQUIRED_INPUTS,
    steps=HEAT_PUMP_STEAM_STEPS,
    input_constraints=salt_temperature_constraints(),
)

# 自动注册进管道全局注册表
pipeline_registry.register(industrial_heat_pump_steam_pipeline)
