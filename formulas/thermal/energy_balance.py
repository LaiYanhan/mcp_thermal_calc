"""
热平衡与储能热负荷原子公式 (Thermal Energy Balance Formulas)
基于图1流程与《输入输出2.xlsx》计算表，包含代数解析公式，基于 SymPy 支持自动多向推导求解。
"""

from core.formula import AlgebraicFormula, default_formula_registry
from core.types import FormulaMetadata, FormulaType, Pin

# ================= 1. 进出口焓差计算 =================
# 公式：蒸汽焓值 - 给水焓值 = 焓差
enthalpy_diff_formula = AlgebraicFormula(
    metadata=FormulaMetadata(
        id="thermal.enthalpy_diff",
        name="蒸汽进出口焓差计算",
        category="thermal",
        description="计算蒸汽发生系统工质进出口比焓增量（焓差），反映每公斤水吸热相变为蒸汽所需吸收的热量。",
        notes="焓差必须大于 0；若计算出负值或异常极小值说明给水参数异常或高于蒸汽参数。",
        formula_type=FormulaType.ALGEBRAIC,
        inputs=[
            Pin("steam_enthalpy", "kJ/kg", "产出蒸汽比焓", min_value=1000.0, max_value=4000.0),
            Pin("feedwater_enthalpy", "kJ/kg", "入口给水比焓", min_value=10.0, max_value=1000.0),
        ],
        outputs=[
            Pin("enthalpy_diff", "kJ/kg", "进出口有效焓差", min_value=100.0, max_value=3500.0)
        ],
        expression="enthalpy_diff = steam_enthalpy - feedwater_enthalpy",
        is_bidirectional=True,
    ),
    equation_str="enthalpy_diff = steam_enthalpy - feedwater_enthalpy",
)


# ================= 2. SGS 换热功率计算 =================
# 公式：蒸汽流量 * 进出口有效焓差 / 3600 = SGS换热功率
# 单位推导：(t/h) * (kJ/kg) / 3600 = (1000 kg / 3600 s) * (kJ/kg) = kW；kW / 1000 = MW
sgs_power_formula = AlgebraicFormula(
    metadata=FormulaMetadata(
        id="thermal.sgs_power",
        name="SGS蒸汽发生器换热功率计算",
        category="thermal",
        description="根据额定蒸汽质量流量与进出口焓差，计算蒸汽发生器（SGS）的瞬态热功率负荷（MWt）。",
        notes="除以 3600 为物理单位转换系数：(t/h)*(kJ/kg) 转换为 MWt。图1核心节点，对应连续热功率需求。",
        formula_type=FormulaType.ALGEBRAIC,
        inputs=[
            Pin("steam_mass_flow", "t/h", "额定蒸汽质量流量", min_value=0.1, max_value=2000.0, default_value=100.0),
            Pin("enthalpy_diff", "kJ/kg", "进出口有效焓差", min_value=100.0, max_value=3500.0),
        ],
        outputs=[
            Pin("sgs_power", "MW", "SGS换热功率需求", min_value=0.1, max_value=2000.0)
        ],
        expression="sgs_power = steam_mass_flow * enthalpy_diff / 3600",
        is_bidirectional=True,
    ),
    equation_str="sgs_power = steam_mass_flow * enthalpy_diff / 3600",
)


# ================= 3. 供汽周期总制热量/吸热量计算 =================
# 公式：SGS换热功率 * 供汽时长 / 换热综合效率 = 供汽期总吸热量
# 参考《计算!D6》：=D5*输入!D7/输入!D13
steam_heat_supply_formula = AlgebraicFormula(
    metadata=FormulaMetadata(
        id="thermal.steam_heat_supply",
        name="供汽期总吸热量（制热量）计算",
        category="thermal",
        description="根据 SGS 功率、每日供汽时长及换热器效率，计算每日产汽期熔盐侧需要向工质释放的总热量（MWh）。",
        notes="考虑了换热器不完全换热损失（除以换热效率 0.99）。",
        formula_type=FormulaType.ALGEBRAIC,
        inputs=[
            Pin("sgs_power", "MW", "SGS瞬态换热功率", min_value=0.1, max_value=2000.0),
            Pin("steam_supply_hours", "h", "每日连续供汽时长", min_value=0.5, max_value=24.0, default_value=8.0),
            Pin("heat_exchanger_efficiency", "/", "换热综合效率", min_value=0.8, max_value=1.0, default_value=0.99),
        ],
        outputs=[
            Pin("steam_heat_supply", "MWh", "每日供汽总释热量", min_value=0.1, max_value=50000.0)
        ],
        expression="steam_heat_supply = sgs_power * steam_supply_hours / heat_exchanger_efficiency",
        is_bidirectional=True,
    ),
    equation_str="steam_heat_supply = sgs_power * steam_supply_hours / heat_exchanger_efficiency",
)


# ================= 4. 储热罐总储热容量计算 =================
# 公式：供汽期总吸热量 / 储热罐保温与储热效率 = 储热罐额定储热量
# 参考《计算!D8》：=D6/输入!D14
thermal_storage_capacity_formula = AlgebraicFormula(
    metadata=FormulaMetadata(
        id="thermal.thermal_storage_capacity",
        name="储热罐额定储热量计算",
        category="thermal",
        description="根据每日所需制热量及储热罐保温与储热效率，计算储罐必须储存的总热量（MWht）。",
        notes="考虑了储罐散热与循环储能损耗（除以储热效率 0.99）。",
        formula_type=FormulaType.ALGEBRAIC,
        inputs=[
            Pin("steam_heat_supply", "MWh", "每日供汽总释热量", min_value=0.1, max_value=50000.0),
            Pin("thermal_storage_efficiency", "/", "储热罐保温与储热效率", min_value=0.8, max_value=1.0, default_value=0.99),
        ],
        outputs=[
            Pin("thermal_storage_capacity", "MWh", "储热罐额定储热容量", min_value=0.1, max_value=60000.0)
        ],
        expression="thermal_storage_capacity = steam_heat_supply / thermal_storage_efficiency",
        is_bidirectional=True,
    ),
    equation_str="thermal_storage_capacity = steam_heat_supply / thermal_storage_efficiency",
)


# ================= 5. 电加热器功率计算（时长解耦） =================
# 公式：供汽期总吸热量 / 谷电时长 / 电加热器电热效率 = 电加热器额定电功率
# 参考《计算!D7》：=D6/输入!D8/输入!D10
electric_heater_power_formula = AlgebraicFormula(
    metadata=FormulaMetadata(
        id="thermal.electric_heater_power",
        name="电加热器额定电功率计算",
        category="thermal",
        description="根据每日蓄热需求、谷电蓄热时间窗口与电加热器电热转化效率，计算电加热器所需额定电功率（MWe）。",
        notes="图1手写重点标注：供汽时长与谷电时长在此完全解耦，以总能量守恒折算加热功率。",
        formula_type=FormulaType.ALGEBRAIC,
        inputs=[
            Pin("steam_heat_supply", "MWh", "每日供汽总释热量", min_value=0.1, max_value=50000.0),
            Pin("valley_electricity_hours", "h", "每日低谷电蓄热时长", min_value=0.5, max_value=24.0, default_value=8.0),
            Pin("electric_heater_efficiency", "/", "电加热器电热转换效率", min_value=0.8, max_value=1.0, default_value=0.985),
        ],
        outputs=[
            Pin("electric_heater_power", "MW", "电加热器所需电功率", min_value=0.1, max_value=2000.0)
        ],
        expression="electric_heater_power = steam_heat_supply / valley_electricity_hours / electric_heater_efficiency",
        is_bidirectional=True,
    ),
    equation_str="electric_heater_power = steam_heat_supply / valley_electricity_hours / electric_heater_efficiency",
)


# ================= 6. 熔盐总装填量计算 =================
# 公式：储热罐额定储热量 * 3600 / (熔盐平均比热容 * (高温熔盐温度 - 低温熔盐温度)) * 设计安全冗余系数 = 熔盐装填总质量
# 参考《选型!D9》：=ROUNDUP(D4*3600/D8/(D6-D7)*1.1, -1)
# 单位：(MWh * 3600 MJ/MWh * 1000 kJ/MJ) / (kJ/kg * (Th-Tc)) = kg / 1000 = t
molten_salt_mass_formula = AlgebraicFormula(
    metadata=FormulaMetadata(
        id="thermal.molten_salt_mass",
        name="储热熔盐需求总质量计算",
        category="thermal",
        description="根据储热容量、熔盐高低温工作温差、介质平均定压比热容及工程安全冗余系数，计算所需熔盐净重（t）。",
        notes="工程设计中通常预留 10%（*1.10）作为罐底未排净死盐量及热工波动冗余。",
        formula_type=FormulaType.ALGEBRAIC,
        inputs=[
            Pin("thermal_storage_capacity", "MWh", "储热罐额定储热容量", min_value=0.1, max_value=60000.0),
            Pin("salt_specific_heat", "kJ/(kg·℃)", "熔盐平均定压比热容", min_value=1.0, max_value=3.0, default_value=1.42),
            Pin("salt_hot_temperature", "℃", "高温熔盐工作温度", min_value=180.0, max_value=600.0, default_value=390.0),
            Pin("salt_cold_temperature", "℃", "低温熔盐工作温度", min_value=140.0, max_value=450.0, default_value=190.0),
            Pin("salt_safety_margin", "/", "工程设计冗余系数", min_value=1.0, max_value=1.5, default_value=1.10),
        ],
        outputs=[
            Pin("salt_mass", "t", "熔盐装填总质量", min_value=1.0, max_value=1000000.0)
        ],
        expression="salt_mass = thermal_storage_capacity * 3600 / (salt_specific_heat * (salt_hot_temperature - salt_cold_temperature)) * salt_safety_margin",
        is_bidirectional=True,
    ),
    equation_str="salt_mass = thermal_storage_capacity * 3600 / (salt_specific_heat * (salt_hot_temperature - salt_cold_temperature)) * salt_safety_margin",
)


# 注册所有热平衡公式
default_formula_registry.register(enthalpy_diff_formula)
default_formula_registry.register(sgs_power_formula)
default_formula_registry.register(steam_heat_supply_formula)
default_formula_registry.register(thermal_storage_capacity_formula)
default_formula_registry.register(electric_heater_power_formula)
default_formula_registry.register(molten_salt_mass_formula)
