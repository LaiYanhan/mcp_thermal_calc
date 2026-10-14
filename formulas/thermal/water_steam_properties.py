"""
水和水蒸气热力学物性查表公式 (IAPWS-IF97 Water & Steam Thermodynamic Properties)
封装 IAPWS-IF97 国际水蒸气热力学状态方程。
"""

from pyXSteam.XSteam import XSteam
from core.formula import EmpiricalFormula, default_formula_registry
from core.types import FormulaMetadata, FormulaType, Pin

# 初始化 IAPWS-IF97 MKS 物性计算器 (P单位: bar, T单位: ℃, h单位: kJ/kg)
_xsteam = XSteam(XSteam.UNIT_SYSTEM_MKS)


def _calc_steam_enthalpy(inputs: dict) -> dict:
    p_mpa = inputs["steam_pressure"]
    t_c = inputs["steam_temperature"]
    # 1 MPa = 10 bar
    p_bar = p_mpa * 10.0
    h_kj_kg = float(_xsteam.h_pt(p_bar, t_c))
    return {"steam_enthalpy": h_kj_kg}

# ================= 1. 蒸汽焓值查表计算 =================
# 公式：根据 (蒸汽工作压力, 蒸汽工作温度) 查IAPWS水蒸气物性表 = 蒸汽比焓
steam_enthalpy_formula = EmpiricalFormula(
    metadata=FormulaMetadata(
        id="thermal.steam_enthalpy",
        name="蒸汽焓值查表计算",
        category="thermal",
        description="基于 IAPWS-IF97 国际水蒸气热力学状态方程，根据蒸汽工作压力与温度确定过热/饱和蒸汽比焓值。",
        notes="输入压力必须换算为绝对工作压力；若为湿饱和蒸汽需关注干度，目前默认过热或饱和单相蒸汽区。",
        formula_type=FormulaType.EMPIRICAL,
        inputs=[
            Pin(
                name="steam_pressure",
                unit="MPa",
                description="蒸汽工作压力（MPa）",
                min_value=0.1,
                max_value=25.0,
                default_value=1.5,
            ),
            Pin(
                name="steam_temperature",
                unit="℃",
                description="蒸汽工作温度（℃）",
                min_value=100.0,
                max_value=600.0,
                default_value=200.0,
            ),
        ],
        outputs=[
            Pin(
                name="steam_enthalpy",
                unit="kJ/kg",
                description="蒸汽比焓（kJ/kg）",
                min_value=1000.0,
                max_value=4000.0,
            )
        ],
        is_bidirectional=False,
    ),
    func=_calc_steam_enthalpy,
)


def _calc_water_enthalpy(inputs: dict) -> dict:
    p_mpa = inputs["feedwater_pressure"]
    t_c = inputs["feedwater_temperature"]
    p_bar = p_mpa * 10.0
    h_kj_kg = float(_xsteam.h_pt(p_bar, t_c))
    return {"feedwater_enthalpy": h_kj_kg}


# ================= 2. 给水焓值查表计算 =================
# 公式：根据 (给水压力, 给水温度) 查IAPWS水蒸气物性表 = 给水比焓
water_enthalpy_formula = EmpiricalFormula(
    metadata=FormulaMetadata(
        id="thermal.water_enthalpy",
        name="给水焓值查表计算",
        category="thermal",
        description="基于 IAPWS-IF97 国际水蒸气热力学状态方程，根据锅炉给水压力与给水温度计算给水初始比焓值。",
        notes="给水通常为过冷未饱和水，压力对水比焓影响较小，温度为主要决定因素。",
        formula_type=FormulaType.EMPIRICAL,
        inputs=[
            Pin(
                name="feedwater_pressure",
                unit="MPa",
                description="给水压力（MPa）",
                min_value=0.05,
                max_value=25.0,
                default_value=0.1,
            ),
            Pin(
                name="feedwater_temperature",
                unit="℃",
                description="给水温度（℃）",
                min_value=5.0,
                max_value=150.0,
                default_value=20.0,
            ),
        ],
        outputs=[
            Pin(
                name="feedwater_enthalpy",
                unit="kJ/kg",
                description="给水比焓（kJ/kg）",
                min_value=10.0,
                max_value=1000.0,
            )
        ],
        is_bidirectional=False,
    ),
    func=_calc_water_enthalpy,
)

# 自动注册
default_formula_registry.register(steam_enthalpy_formula)
default_formula_registry.register(water_enthalpy_formula)
