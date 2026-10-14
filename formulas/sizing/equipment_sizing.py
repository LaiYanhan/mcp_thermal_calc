"""
设备离散选型原子公式 (Discrete Equipment Sizing Formulas)
遵循 ADR 0003，将设备整定选型规则抽象为标准原子公式节点，平铺融入计算流水线。
"""

import math
from constants.equipment_catalog import (
    snap_sgs_power,
    snap_heater_power,
    snap_transformer_capacity,
)
from core.formula import EmpiricalFormula, default_formula_registry
from core.types import FormulaMetadata, FormulaType, Pin


# ================= 1. SGS 换热器选型 =================
# 公式：SGS理论换热功率需求 向上整定至5MW模数 = SGS标准选型规格
def _calc_sgs_sizing(inputs: dict) -> dict:
    raw_mw = inputs["sgs_power"]
    sized_mw = snap_sgs_power(raw_mw)
    return {"sgs_sizing_mw": sized_mw}


sgs_sizing_formula = EmpiricalFormula(
    metadata=FormulaMetadata(
        id="sizing.sgs_sizing",
        name="SGS蒸汽发生器规格整定选型",
        category="sizing",
        description="根据理论计算的 SGS 换热功率需求，按制造商标准化规格（每5MW为一档）向上圆整确定选型型号。",
        notes="按制造商5MW标准步长向上圆整。",
        formula_type=FormulaType.EMPIRICAL,
        inputs=[
            Pin("sgs_power", "MW", "SGS理论换热功率需求", min_value=0.1, max_value=2000.0)
        ],
        outputs=[
            Pin("sgs_sizing_mw", "MW", "SGS标准选型规格", min_value=5.0, max_value=2000.0)
        ],
        is_bidirectional=False,
    ),
    func=_calc_sgs_sizing,
)


# ================= 2. 电加热器规格选型 =================
# 公式：电加热器理论电功率需求 向上整定至5MW模数 = 电加热器标准选型规格
def _calc_heater_sizing(inputs: dict) -> dict:
    raw_mw = inputs["electric_heater_power"]
    sized_mw = snap_heater_power(raw_mw)
    return {"heater_sizing_mw": sized_mw}


heater_sizing_formula = EmpiricalFormula(
    metadata=FormulaMetadata(
        id="sizing.heater_sizing",
        name="电加热器规格整定选型",
        category="sizing",
        description="根据理论电加热功率需求，按标准模块（5MW模数）向上整定选型规格。",
        notes="按5MW标准电加热模块向上整定选型。",
        formula_type=FormulaType.EMPIRICAL,
        inputs=[
            Pin("electric_heater_power", "MW", "电加热器理论电功率需求", min_value=0.1, max_value=2000.0)
        ],
        outputs=[
            Pin("heater_sizing_mw", "MW", "电加热器标准选型规格", min_value=5.0, max_value=2000.0)
        ],
        is_bidirectional=False,
    ),
    func=_calc_heater_sizing,
)


# ================= 3. 变压器标准容量选型 =================
# 公式：根据电加热器选型功率查国家标准变压器序列向上匹配 = 主变压器标准额定容量
def _calc_transformer_sizing(inputs: dict) -> dict:
    heater_mw = inputs["heater_sizing_mw"]
    # 电加热器方案功率因数按 1.0
    cap_mva = snap_transformer_capacity(heater_mw, power_factor=1.0)
    return {"transformer_capacity_mva": cap_mva}


transformer_sizing_formula = EmpiricalFormula(
    metadata=FormulaMetadata(
        id="sizing.transformer_sizing",
        name="主变压器标准容量查表选型",
        category="sizing",
        description="根据电加热器选型功率（功率因数取1.0），从国家标准变压器容量序列 [6.3, 8, 10, 12.5, 16, 20, 25, 31.5, 40, 50, 63, 90, 120] MVA 中向上匹配最接近的标准容量。",
        notes="若计算容量超过 120 MVA，建议采用多台变压器组合。",
        formula_type=FormulaType.EMPIRICAL,
        inputs=[
            Pin("heater_sizing_mw", "MW", "电加热器选型功率", min_value=1.0, max_value=2000.0)
        ],
        outputs=[
            Pin("transformer_capacity_mva", "MVA", "主变压器标准额定容量", min_value=6.3, max_value=5000.0)
        ],
        is_bidirectional=False,
    ),
    func=_calc_transformer_sizing,
)


# ================= 4. 熔盐量工程圆整选型 =================
# 公式：理论熔盐装填量 向上取整至整10吨 = 工程整定熔盐订购量
def _calc_salt_mass_roundup(inputs: dict) -> dict:
    raw_mass = inputs["salt_mass"]
    # 向上取整到 10 吨整数倍
    rounded = math.ceil(raw_mass / 10.0) * 10.0
    return {"salt_mass_tons": rounded}


salt_mass_roundup_formula = EmpiricalFormula(
    metadata=FormulaMetadata(
        id="sizing.salt_mass_roundup",
        name="熔盐订货量工程整定",
        category="sizing",
        description="将理论计算熔盐净重向上圆整至整10吨，便于设备罐容设计与大宗原材料采购订货。",
        notes="",
        formula_type=FormulaType.EMPIRICAL,
        inputs=[
            Pin("salt_mass", "t", "理论熔盐装填量", min_value=1.0, max_value=1000000.0)
        ],
        outputs=[
            Pin("salt_mass_tons", "t", "工程整定熔盐订购量", min_value=10.0, max_value=1000000.0)
        ],
        is_bidirectional=False,
    ),
    func=_calc_salt_mass_roundup,
)


# 注册所有选型公式
default_formula_registry.register(sgs_sizing_formula)
default_formula_registry.register(heater_sizing_formula)
default_formula_registry.register(transformer_sizing_formula)
default_formula_registry.register(salt_mass_roundup_formula)
