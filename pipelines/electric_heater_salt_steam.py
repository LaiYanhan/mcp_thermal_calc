"""
基准计算管道：电加热器熔盐储热供汽场景 (Electric Heater with Molten Salt Storage Steam Supply Pipeline)、

场景标识: scenario_electric_heater_salt_steam
场景名称: 电加热器熔盐储热供汽场景
所属分类: electric_heater_salt_steam
"""

from constants.default_parameters import DEFAULT_VALLEY_SALT_STEAM_PARAMS
from core.pipeline import Pipeline, PipelineStep, pipeline_registry
from core.types import Pin
from pipelines.validation import salt_temperature_constraints


def _get_pin(key: str) -> Pin:
    cfg = DEFAULT_VALLEY_SALT_STEAM_PARAMS[key]
    return Pin(
        name=key,
        unit=cfg["unit"],
        description=cfg["description"],
        min_value=cfg["min_value"],
        max_value=cfg["max_value"],
        default_value=cfg["value"],
        kind="constant" if key in ("electric_heater_efficiency", "heat_exchanger_efficiency", "thermal_storage_efficiency", "salt_specific_heat", "salt_safety_margin") else "input",
    )


# 1. 声明该管道必需的所有工况输入与常量参数
ELECTRIC_HEATER_SALT_STEAM_REQUIRED_INPUTS = [
    _get_pin("steam_pressure"),              # 蒸汽绝对工作压力 (基准默认 1.5 MPa)
    _get_pin("steam_temperature"),           # 蒸汽供汽温度 (基准默认 200.0 ℃)
    _get_pin("steam_mass_flow"),             # 额定蒸汽瞬时质量流量 (基准默认 100.0 t/h)
    _get_pin("feedwater_pressure"),          # 换热器/锅炉给水绝对压力 (基准默认 0.1 MPa)
    _get_pin("feedwater_temperature"),       # 给水水温 (基准默认 20.0 ℃)
    _get_pin("steam_supply_hours"),          # 每日连续供汽时长 (基准默认 8.0 h)
    _get_pin("valley_electricity_hours"),    # 每日低谷电蓄热时长 (基准默认 8.0 h)
    _get_pin("annual_operating_days"),       # 年有效运行天数 (基准默认 330.0 d)
    _get_pin("electric_heater_efficiency"),  # 电加热器电热转换综合效率 (工程常量，默认 0.985)
    _get_pin("heat_exchanger_efficiency"),   # SGS换热器换热综合效率 (工程常量，默认 0.99)
    _get_pin("thermal_storage_efficiency"),  # 熔盐储热罐保温与储热效率 (工程常量，默认 0.99)
    _get_pin("salt_hot_temperature"),        # 储热高温熔盐工作温度 (HITEC盐默认 390.0 ℃)
    _get_pin("salt_cold_temperature"),       # 储热低温熔盐工作温度 (HITEC盐默认 190.0 ℃)
    _get_pin("salt_specific_heat"),          # 熔盐平均定压比热容 (工程常量，默认 1.42 kJ/(kg·℃))
    _get_pin("salt_safety_margin"),          # 熔盐设计安全冗余系数 (工程常量，默认 1.10)
    _get_pin("valley_electricity_price"),    # 当地工业低谷电价 (基准默认 0.30 元/kWh)
    _get_pin("steam_market_price"),          # 当地工业蒸汽销售单价 (基准默认 180.0 元/t)
]

# 2. 声明有向无环图（DAG）拓扑连接步骤序列
ELECTRIC_HEATER_SALT_STEAM_STEPS = [
    # 步骤 1: 查表确定蒸汽比焓
    PipelineStep(
        step_id="step_1_steam_enthalpy",
        formula_id="thermal.steam_enthalpy",
        input_map={"steam_pressure": "steam_pressure", "steam_temperature": "steam_temperature"},
        output_map={"steam_enthalpy": "steam_enthalpy"},
        description="根据蒸汽压力和温度，基于 IAPWS-95 物性库查表计算蒸汽比焓",
    ),
    # 步骤 2: 查表确定给水比焓
    PipelineStep(
        step_id="step_2_water_enthalpy",
        formula_id="thermal.water_enthalpy",
        input_map={"feedwater_pressure": "feedwater_pressure", "feedwater_temperature": "feedwater_temperature"},
        output_map={"feedwater_enthalpy": "feedwater_enthalpy"},
        description="根据给水压力和温度，基于 IAPWS-95 物性库查表计算给水比焓",
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
    # 步骤 8: 计算电加热器所需电功率
    PipelineStep(
        step_id="step_8_electric_heater_power",
        formula_id="thermal.electric_heater_power",
        input_map={
            "thermal_storage_capacity": "thermal_storage_capacity",
            "valley_electricity_hours": "valley_electricity_hours",
            "electric_heater_efficiency": "electric_heater_efficiency",
        },
        output_map={"electric_heater_power": "electric_heater_power"},
        description="基于总能量守恒与谷电蓄热时长窗口，折算电加热器额定电功率（MWe）",
    ),
    # 步骤 9: 计算熔盐需求量
    PipelineStep(
        step_id="step_9_molten_salt_mass",
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
    # 步骤 10: 熔盐采购量工程整定
    PipelineStep(
        step_id="step_10_salt_mass_roundup",
        formula_id="sizing.salt_mass_roundup",
        input_map={"salt_mass": "salt_mass"},
        output_map={"salt_mass_tons": "salt_mass_tons"},
        description="理论熔盐净重向上圆整至整 10 吨采购订货量",
    ),
    # 步骤 11: 每日消纳谷电量计算
    PipelineStep(
        step_id="step_11_daily_electricity",
        formula_id="operation.daily_electricity",
        input_map={
            "electric_heater_power": "electric_heater_power",
            "valley_electricity_hours": "valley_electricity_hours",
        },
        output_map={"daily_power_mwh": "daily_power_mwh"},
        description="计算每日消纳低谷电用电量（MWh/d）",
    ),
    # 步骤 12: 年累计消纳电量计算
    PipelineStep(
        step_id="step_12_annual_electricity",
        formula_id="operation.annual_electricity",
        input_map={
            "daily_power_mwh": "daily_power_mwh",
            "annual_operating_days": "annual_operating_days",
        },
        output_map={"annual_power_wan_kwh": "annual_power_wan_kwh"},
        description="按年有效运营天数测算年累计用电量（万kWh/年）",
    ),
    # 步骤 13: 每日供汽总量计算
    PipelineStep(
        step_id="step_13_daily_steam_production",
        formula_id="operation.daily_steam_production",
        input_map={
            "steam_mass_flow": "steam_mass_flow",
            "steam_supply_hours": "steam_supply_hours",
        },
        output_map={"daily_steam_tons": "daily_steam_tons"},
        description="计算每日累计外供蒸汽吨数（t/d）",
    ),
    # 步骤 14: 年累计供汽量计算
    PipelineStep(
        step_id="step_14_annual_steam_production",
        formula_id="operation.annual_steam_production",
        input_map={
            "daily_steam_tons": "daily_steam_tons",
            "annual_operating_days": "annual_operating_days",
        },
        output_map={"annual_steam_wan_tons": "annual_steam_wan_tons"},
        description="测算年累计外供蒸汽量（万t/年）",
    ),
    # 步骤 15: 每日购电成本计算
    PipelineStep(
        step_id="step_15_daily_electricity_cost",
        formula_id="operation.daily_electricity_cost",
        input_map={
            "daily_power_mwh": "daily_power_mwh",
            "valley_electricity_price": "valley_electricity_price",
        },
        output_map={"daily_electricity_cost": "daily_electricity_cost"},
        description="计算每日谷电购电费用支出（元/d）",
    ),
    # 步骤 16: 每日售汽收入计算
    PipelineStep(
        step_id="step_16_daily_steam_revenue",
        formula_id="operation.daily_steam_revenue",
        input_map={
            "daily_steam_tons": "daily_steam_tons",
            "steam_market_price": "steam_market_price",
        },
        output_map={"daily_steam_revenue": "daily_steam_revenue"},
        description="计算每日外供蒸汽营业收入（元/d）",
    ),
    # 步骤 17: 每日经营毛收益差额计算
    PipelineStep(
        step_id="step_17_daily_operating_spread",
        formula_id="operation.daily_operating_spread",
        input_map={
            "daily_steam_revenue": "daily_steam_revenue",
            "daily_electricity_cost": "daily_electricity_cost",
        },
        output_map={"daily_operating_spread": "daily_operating_spread"},
        description="计算日度售汽收入与低谷购电成本的毛利差额（元/d）",
    ),
]

electric_heater_salt_steam_pipeline = Pipeline(
    id="scenario_electric_heater_salt_steam",
    name="电加热器熔盐储热供汽计算场景",
    category="molten_salt_steam",
    description=(
        "该项目为电加热器熔盐储热供汽工程场景。利用夜间低谷电价时段启动电阻式电加热器将熔盐加热储存，"
        "储热时长通常为8h；在白天用热时段通过熔盐蒸汽发生系统（SGS）连续供应工业蒸汽。"
        "实现源侧/用户侧削峰填谷、消纳低成本绿电或谷电、替代燃煤燃气锅炉供汽。"
    ),
    notes=(
        "1. 供汽时长与谷电时长已完全解耦，若时长不等，系统将依据能量守恒自动折算电加热功率；\n"
        "2. 默认采用中温 HITEC 三元盐（190~390℃），若工况为超临界或超高温蒸汽，需切换为太阳盐温区；\n"
        "3. 本流程经营毛利未扣减水耗、厂用动力电及人工折旧，深度财务测算待后续扩展。"
    ),
    required_inputs=ELECTRIC_HEATER_SALT_STEAM_REQUIRED_INPUTS,
    steps=ELECTRIC_HEATER_SALT_STEAM_STEPS,
    input_constraints=salt_temperature_constraints("HITEC"),
)

# 自动注册进管道注册表
pipeline_registry.register(electric_heater_salt_steam_pipeline)

