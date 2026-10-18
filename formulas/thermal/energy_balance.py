"""
热平衡与储能热负荷原子公式 (Thermal Energy Balance Formulas)
包含进出口焓差、理论产汽功率、SGS换热功率、供汽总热量、储热容量、电加热功率与熔盐质量计算。
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


# ================= 2. 理论产汽功率计算 =================
# 公式：蒸汽流量 * 进出口有效焓差 / 3600 = 理论产汽功率
# 单位推导：(t/h) * (kJ/kg) / 3600 = (1000 kg / 3600 s) * (kJ/kg) = kW；kW / 1000 = MW
theoretical_power_formula = AlgebraicFormula(
    metadata=FormulaMetadata(
        id="thermal.theoretical_power",
        name="理论产汽功率计算",
        category="thermal",
        description="在额定参数下产生这些蒸汽所需的理论净吸热功率（MWt）。",
        notes="除以 3600 为物理单位转换系数：(t/h)*(kJ/kg) 转换为 MWt。",
        formula_type=FormulaType.ALGEBRAIC,
        inputs=[
            Pin("steam_mass_flow", "t/h", "额定蒸汽质量流量", min_value=0.1, max_value=2000.0, default_value=100.0),
            Pin("enthalpy_diff", "kJ/kg", "进出口有效焓差", min_value=100.0, max_value=3500.0),
        ],
        outputs=[
            Pin("theoretical_power", "MW", "理论产汽功率", min_value=0.1, max_value=2000.0)
        ],
        expression="theoretical_power = steam_mass_flow * enthalpy_diff / 3600",
        is_bidirectional=True,
    ),
    equation_str="theoretical_power = steam_mass_flow * enthalpy_diff / 3600",
)


# ================= 3. SGS 换热功率计算 =================
# 公式：理论产汽功率 / 换热综合效率 = SGS换热功率
sgs_power_formula = AlgebraicFormula(
    metadata=FormulaMetadata(
        id="thermal.sgs_power",
        name="SGS蒸汽发生器换热功率计算",
        category="thermal",
        description="计入换热器换热损失后，实际生产蒸汽所需的SGS换热器侧热功率（MWt）。",
        notes="",
        formula_type=FormulaType.ALGEBRAIC,
        inputs=[
            Pin("theoretical_power", "MW", "理论产汽功率", min_value=0.1, max_value=2000.0),
            Pin("heat_exchanger_efficiency", "/", "换热综合效率", min_value=0.8, max_value=1.0, default_value=0.99),
        ],
        outputs=[
            Pin("sgs_power", "MW", "SGS实际换热功率", min_value=0.1, max_value=2000.0)
        ],
        expression="sgs_power = theoretical_power / heat_exchanger_efficiency",
        is_bidirectional=True,
    ),
    equation_str="sgs_power = theoretical_power / heat_exchanger_efficiency",
)


# ================= 4. 供汽周期总吸热量（能量转换） =================
# 公式：SGS换热功率 * 供汽时长 = 供汽期总吸热量
steam_heat_supply_formula = AlgebraicFormula(
    metadata=FormulaMetadata(
        id="thermal.steam_heat_supply",
        name="供汽期总吸热量计算",
        category="thermal",
        description="根据SGS实际换热功率与供汽时长，将功率转换为供汽周期累计所需释放的总热能量（MWh）。",
        notes="",
        formula_type=FormulaType.ALGEBRAIC,
        inputs=[
            Pin("sgs_power", "MW", "SGS实际换热功率", min_value=0.1, max_value=2000.0),
            Pin("steam_supply_hours", "h", "每日连续供汽时长", min_value=0.5, max_value=24.0, default_value=8.0),
        ],
        outputs=[
            Pin("steam_heat_supply", "MWh", "每日供汽总释热量", min_value=0.1, max_value=50000.0)
        ],
        expression="steam_heat_supply = sgs_power * steam_supply_hours",
        is_bidirectional=True,
    ),
    equation_str="steam_heat_supply = sgs_power * steam_supply_hours",
)


# ================= 5. 储热罐总储热容量计算 =================
# 公式：供汽期总吸热量 / 储热罐保温与储热效率 = 储热罐额定储热量
thermal_storage_capacity_formula = AlgebraicFormula(
    metadata=FormulaMetadata(
        id="thermal.thermal_storage_capacity",
        name="储热罐额定储热量计算",
        category="thermal",
        description="供汽期总吸热能量计入储罐保温散热与储热循环损失后，储罐所需储存的总热能量（MWht）。",
        notes="",
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


# ================= 6. 电加热器功率计算（时长解耦） =================
# 公式：储热罐额定储热量 / 谷电时长 / 电加热器电热效率 = 电加热器额定电功率
electric_heater_power_formula = AlgebraicFormula(
    metadata=FormulaMetadata(
        id="thermal.electric_heater_power",
        name="电加热器额定电功率计算",
        category="thermal",
        description="基于储热总能量在谷电时间窗口内完成蓄热的能量守恒，折算电加热器额定电功率（MWe）。",
        notes="供汽时长与谷电时长已解耦，基于总储热能量除以谷电时长折算。",
        formula_type=FormulaType.ALGEBRAIC,
        inputs=[
            Pin("thermal_storage_capacity", "MWh", "储热罐额定储热容量", min_value=0.1, max_value=60000.0),
            Pin("valley_electricity_hours", "h", "每日低谷电蓄热时长", min_value=0.5, max_value=24.0, default_value=8.0),
            Pin("electric_heater_efficiency", "/", "电加热器电热转换效率", min_value=0.8, max_value=1.0, default_value=0.985),
        ],
        outputs=[
            Pin("electric_heater_power", "MW", "电加热器所需电功率", min_value=0.1, max_value=2000.0)
        ],
        expression="electric_heater_power = thermal_storage_capacity / valley_electricity_hours / electric_heater_efficiency",
        is_bidirectional=True,
    ),
    equation_str="electric_heater_power = thermal_storage_capacity / valley_electricity_hours / electric_heater_efficiency",
)


# ================= 7. 熔盐总装填量计算 =================
# 公式：储热罐额定储热量 * 3600 / (熔盐平均比热容 * (高温熔盐温度 - 低温熔盐温度)) * 设计安全冗余系数 = 熔盐装填总质量
# 单位推导：(MWh * 3600 MJ/MWh * 1000 kJ/MJ) / (kJ/kg * (Th-Tc)) = kg / 1000 = t
molten_salt_mass_formula = AlgebraicFormula(
    metadata=FormulaMetadata(
        id="thermal.molten_salt_mass",
        name="储热熔盐需求总质量计算",
        category="thermal",
        description="根据储罐储热总容量、熔盐高低温工作温差、介质平均定压比热容及工程安全冗余系数，计算所需熔盐净重（t）。",
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

# ================= 8. 热泵输出功率计算 =================
# 公式：储热罐额定储热量 / 谷电时长 = 热泵输出热功率
heat_pump_thermal_power = AlgebraicFormula(
    metadata=FormulaMetadata(
        id="thermal.heat_pump_thermal_power",
        name="热泵额定制热热功率计算",
        category="thermal",
        description="基于储热总能量在谷电时间窗口内完成蓄热的能量守恒，折算热泵输出热功率（MWt）。",
        notes="供汽时长与谷电时长已解耦，基于总储热能量除以谷电时长折算。",
        formula_type=FormulaType.ALGEBRAIC,
        inputs=[
            Pin("thermal_storage_capacity", "MWh", "储热罐额定储热容量", min_value=0.1, max_value=60000.0),
            Pin("valley_electricity_hours", "h", "每日低谷电蓄热时长", min_value=0.5, max_value=24.0, default_value=8.0),
        ],
        outputs=[
            Pin("heat_pump_thermal_power", "MWt", "热泵输出热功率", min_value=0.1, max_value=2000.0)
        ],
        expression="heat_pump_thermal_power = thermal_storage_capacity / valley_electricity_hours",
        is_bidirectional=True,
    ),
    equation_str="heat_pump_thermal_power = thermal_storage_capacity / valley_electricity_hours",
)

# ================= 9. 热泵输入电功率计算 =================
# 热泵输出热功率 / COP = 热泵输入电功率
heat_pump_electric_power = AlgebraicFormula(
    metadata=FormulaMetadata(
        id="thermal.heat_pump_electric_power",
        name="热泵额定输入电功率计算",
        category="thermal",
        description="基于储热总能量在谷电时间窗口内完成蓄热的能量守恒，折算热泵输入电功率（MWe）。",
        notes="供汽时长与谷电时长已解耦，基于总储热能量除以谷电时长折算。",
        formula_type=FormulaType.ALGEBRAIC,
        inputs=[
            Pin("heat_pump_thermal_power", "MWt", "热泵输出热功率", min_value=0.1, max_value=2000.0),
            Pin("heat_pump_cop", "/", "热泵COP", min_value=1.0, max_value=10.0, default_value=1.5),
        ],
        outputs=[
            Pin("heat_pump_electric_power", "MWe", "热泵输入电功率", min_value=0.1, max_value=2000.0)
        ],
        expression="heat_pump_electric_power = heat_pump_thermal_power / heat_pump_cop",
        is_bidirectional=True,
    ),
    equation_str="heat_pump_electric_power = heat_pump_thermal_power / heat_pump_cop",
)



# 注册所有热平衡公式
default_formula_registry.register(enthalpy_diff_formula)
default_formula_registry.register(theoretical_power_formula)
default_formula_registry.register(sgs_power_formula)
default_formula_registry.register(steam_heat_supply_formula)
default_formula_registry.register(thermal_storage_capacity_formula)
default_formula_registry.register(electric_heater_power_formula)
default_formula_registry.register(molten_salt_mass_formula)
default_formula_registry.register(heat_pump_thermal_power)
default_formula_registry.register(heat_pump_electric_power)