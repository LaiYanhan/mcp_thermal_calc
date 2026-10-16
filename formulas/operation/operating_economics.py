"""
运行能耗与经营毛收益原子公式 (Operating Consumption & Gross Spread Formulas)
包含消纳电量、供汽总量、购电成本、售汽收入及经营毛收益差额计算。
"""

from core.formula import AlgebraicFormula, default_formula_registry
from core.types import FormulaMetadata, FormulaType, Pin

# ================= 1.1 电热器每日消纳谷电电量计算 =================
# 公式：电加热器运行功率 * 每日谷电时长 = 每日消纳谷电电量
electric_heater_daily_electricity_formula = AlgebraicFormula(
    metadata=FormulaMetadata(
        id="operation.electric_heater_daily_electricity",
        name="电热器日消纳谷电电量计算",
        category="operation",
        description="根据电加热器运行功率与每日谷电蓄热时长，计算每日电加热器实际消纳的电量（MWh/d）。",
        notes="",
        formula_type=FormulaType.ALGEBRAIC,
        inputs=[
            Pin("electric_heater_power", "MW", "电加热器运行功率", min_value=0.1, max_value=2000.0),
            Pin("valley_electricity_hours", "h", "每日谷电时长", min_value=0.5, max_value=24.0, default_value=8.0),
        ],
        outputs=[
            Pin("daily_power_mwh", "MWh", "每日消纳谷电电量", min_value=0.1, max_value=48000.0)
        ],
        expression="daily_power_mwh = electric_heater_power * valley_electricity_hours",
        is_bidirectional=True,
    ),
    equation_str="daily_power_mwh = electric_heater_power * valley_electricity_hours",
)

# ================= 1.2 热泵每日消纳谷电电量计算 =================
# 公式：热泵输入电功率 * 每日谷电时长 = 每日消纳谷电电量
heat_pump_daily_electricity_formula = AlgebraicFormula(
    metadata=FormulaMetadata(
        id="operation.heat_pump_daily_electricity",
        name="热泵日消纳谷电电量计算",
        category="operation",
        description="根据热泵运行功率与每日谷电蓄热时长，计算每日热泵实际消纳的电量（MWh/d）。",
        notes="",
        formula_type=FormulaType.ALGEBRAIC,
        inputs=[
            Pin("heat_pump_electric_power", "MW", "热泵输入电功率", min_value=0.1, max_value=2000.0),
            Pin("valley_electricity_hours", "h", "每日谷电时长", min_value=0.5, max_value=24.0, default_value=8.0),
        ],
        outputs=[
            Pin("daily_power_mwh", "MWh", "每日消纳谷电电量", min_value=0.1, max_value=48000.0)
        ],
        expression="daily_power_mwh = heat_pump_electric_power * valley_electricity_hours",
        is_bidirectional=True,
    ),
    equation_str="daily_power_mwh = heat_pump_electric_power * valley_electricity_hours",
)

# ================= 2. 年消纳谷电电量计算 =================
# 公式：每日消纳谷电电量 * 年运行天数 / 10 = 年累计用电量
# 单位推导：1 MWh = 1000 kWh = 0.1 万kWh，因此 (MWh * 天) / 10 = 万kWh
annual_electricity_formula = AlgebraicFormula(
    metadata=FormulaMetadata(
        id="operation.annual_electricity",
        name="年消纳谷电电量计算",
        category="operation",
        description="根据日消纳电量与年有效运行天数，测算年用电总量（万kWh/年）。",
        notes="",
        formula_type=FormulaType.ALGEBRAIC,
        inputs=[
            Pin("daily_power_mwh", "MWh", "每日消纳谷电电量", min_value=0.1, max_value=48000.0),
            Pin("annual_operating_days", "d", "年运行天数", min_value=50.0, max_value=365.0, default_value=330.0),
        ],
        outputs=[
            Pin("annual_power_wan_kwh", "万kWh", "年累计用电量", min_value=1.0, max_value=1000000.0)
        ],
        expression="annual_power_wan_kwh = daily_power_mwh * annual_operating_days / 10",
        is_bidirectional=True,
    ),
    equation_str="annual_power_wan_kwh = daily_power_mwh * annual_operating_days / 10",
)


# ================= 3. 每日供汽总量计算 =================
# 公式：蒸汽瞬时流量 * 每日供汽时长 = 每日供汽总量
daily_steam_production_formula = AlgebraicFormula(
    metadata=FormulaMetadata(
        id="operation.daily_steam_production",
        name="日外供蒸汽总量计算",
        category="operation",
        description="根据额定蒸汽流量与每日连续供汽时长，计算每日累计输出的蒸汽吨数（t/d）。",
        notes="",
        formula_type=FormulaType.ALGEBRAIC,
        inputs=[
            Pin("steam_mass_flow", "t/h", "蒸汽瞬时流量", min_value=0.1, max_value=2000.0, default_value=100.0),
            Pin("steam_supply_hours", "h", "每日供汽时长", min_value=0.5, max_value=24.0, default_value=8.0),
        ],
        outputs=[
            Pin("daily_steam_tons", "t", "每日供汽总量", min_value=0.1, max_value=48000.0)
        ],
        expression="daily_steam_tons = steam_mass_flow * steam_supply_hours",
        is_bidirectional=True,
    ),
    equation_str="daily_steam_tons = steam_mass_flow * steam_supply_hours",
)


# ================= 4. 年外供蒸汽总量计算 =================
# 公式：每日供汽总量 * 年运行天数 / 10000 = 年累计供汽总量
annual_steam_production_formula = AlgebraicFormula(
    metadata=FormulaMetadata(
        id="operation.annual_steam_production",
        name="年外供蒸汽总量计算",
        category="operation",
        description="根据每日供汽量与年运行天数，计算年累计供汽量（万t/年）。",
        notes="",
        formula_type=FormulaType.ALGEBRAIC,
        inputs=[
            Pin("daily_steam_tons", "t", "每日供汽总量", min_value=0.1, max_value=48000.0),
            Pin("annual_operating_days", "d", "年运行天数", min_value=50.0, max_value=365.0, default_value=330.0),
        ],
        outputs=[
            Pin("annual_steam_wan_tons", "万t", "年累计供汽总量", min_value=0.01, max_value=2000.0)
        ],
        expression="annual_steam_wan_tons = daily_steam_tons * annual_operating_days / 10000",
        is_bidirectional=True,
    ),
    equation_str="annual_steam_wan_tons = daily_steam_tons * annual_operating_days / 10000",
)


# ================= 5. 每日购电成本计算 =================
# 公式：每日消纳谷电电量 * 1000 * 低谷电价 = 每日购电成本
daily_electricity_cost_formula = AlgebraicFormula(
    metadata=FormulaMetadata(
        id="operation.daily_electricity_cost",
        name="每日购电成本计算",
        category="operation",
        description="根据日耗电量（MWh转化为度数*1000）与低谷电价，计算每日电费支出（元/d）。",
        notes="",
        formula_type=FormulaType.ALGEBRAIC,
        inputs=[
            Pin("daily_power_mwh", "MWh", "每日消纳谷电电量", min_value=0.1, max_value=48000.0),
            Pin("valley_electricity_price", "元/kWh", "低谷电价", min_value=-0.1, max_value=3.0, default_value=0.30),
        ],
        outputs=[
            Pin("daily_electricity_cost", "元", "每日低谷电费支出", min_value=-100000.0, max_value=10000000.0)
        ],
        expression="daily_electricity_cost = daily_power_mwh * 1000 * valley_electricity_price",
        is_bidirectional=True,
    ),
    equation_str="daily_electricity_cost = daily_power_mwh * 1000 * valley_electricity_price",
)


# ================= 6. 每日售汽收入计算 =================
# 公式：每日供汽总量 * 蒸汽市售单价 = 每日售汽收入
daily_steam_revenue_formula = AlgebraicFormula(
    metadata=FormulaMetadata(
        id="operation.daily_steam_revenue",
        name="每日售汽收入计算",
        category="operation",
        description="根据日供汽吨数与市售蒸汽单价，计算每日售汽营业额（元/d）。",
        notes="",
        formula_type=FormulaType.ALGEBRAIC,
        inputs=[
            Pin("daily_steam_tons", "t", "每日供汽总量", min_value=0.1, max_value=48000.0),
            Pin("steam_market_price", "元/t", "蒸汽市售单价", min_value=20.0, max_value=1000.0, default_value=180.0),
        ],
        outputs=[
            Pin("daily_steam_revenue", "元", "每日售汽营业收入", min_value=1.0, max_value=50000000.0)
        ],
        expression="daily_steam_revenue = daily_steam_tons * steam_market_price",
        is_bidirectional=True,
    ),
    equation_str="daily_steam_revenue = daily_steam_tons * steam_market_price",
)


# ================= 7. 每日经营毛收益差额计算 =================
# 公式：每日售汽收入 - 每日购电成本 = 每日经营毛收益差额
daily_operating_spread_formula = AlgebraicFormula(
    metadata=FormulaMetadata(
        id="operation.daily_operating_spread",
        name="每日经营毛收益差额计算",
        category="operation",
        description="每日售汽收入与低谷购电成本的直接差额（毛利空间）（元/d）。",
        notes="",
        formula_type=FormulaType.ALGEBRAIC,
        inputs=[
            Pin("daily_steam_revenue", "元", "每日售汽营业收入", min_value=0.0, max_value=50000000.0),
            Pin("daily_electricity_cost", "元", "每日低谷电费支出", min_value=-100000.0, max_value=10000000.0),
        ],
        outputs=[
            Pin("daily_operating_spread", "元", "每日经营毛收益差额", min_value=-10000000.0, max_value=50000000.0)
        ],
        expression="daily_operating_spread = daily_steam_revenue - daily_electricity_cost",
        is_bidirectional=True,
    ),
    equation_str="daily_operating_spread = daily_steam_revenue - daily_electricity_cost",
)


# ================= 8. 年化经营毛收益差额测算 =================
# 公式：每日经营毛收益差额 * 年运行天数 / 10000 = 年化经营毛收益差额
annual_operating_spread_formula = AlgebraicFormula(
    metadata=FormulaMetadata(
        id="operation.annual_operating_spread",
        name="年化经营毛收益差额测算",
        category="operation",
        description="按年有效运营天数将日度毛利差额折算为年化经营毛利（万元/年）。",
        notes="未扣除除盐水水费、厂用动力电及设备折旧人工。",
        formula_type=FormulaType.ALGEBRAIC,
        inputs=[
            Pin("daily_operating_spread", "元", "每日经营毛收益差额", min_value=-10000000.0, max_value=50000000.0),
            Pin("annual_operating_days", "d", "年运行天数", min_value=50.0, max_value=365.0, default_value=330.0),
        ],
        outputs=[
            Pin("annual_operating_spread_wan", "万元", "年化经营毛收益差额", min_value=-10000.0, max_value=100000.0)
        ],
        expression="annual_operating_spread_wan = daily_operating_spread * annual_operating_days / 10000",
        is_bidirectional=True,
    ),
    equation_str="annual_operating_spread_wan = daily_operating_spread * annual_operating_days / 10000",
)


# 注册所有运行与经济公式
default_formula_registry.register(electric_heater_daily_electricity_formula)
default_formula_registry.register(heat_pump_daily_electricity_formula)
default_formula_registry.register(annual_electricity_formula)
default_formula_registry.register(daily_steam_production_formula)
default_formula_registry.register(annual_steam_production_formula)
default_formula_registry.register(daily_electricity_cost_formula)
default_formula_registry.register(daily_steam_revenue_formula)
default_formula_registry.register(daily_operating_spread_formula)
default_formula_registry.register(annual_operating_spread_formula)
