"""
水和水蒸气热力学物性查表公式 (IAPWS-95 Water & Steam Thermodynamic Properties)
封装 IAPWS-95 国际水蒸气热力学科学基准状态方程。
"""

from iapws import IAPWS95
from core.formula import EmpiricalFormula, default_formula_registry
from core.types import FormulaMetadata, FormulaType, Pin


class _IAPWS95Adapter:
    """IAPWS-95 适配器，向工程公式层与测试暴露统一的 MKS 物理接口 (P: bar, T: ℃, h: kJ/kg)"""

    @staticmethod
    def tsat_p(p_bar: float) -> float:
        p_mpa = p_bar / 10.0
        sat = IAPWS95(P=p_mpa, x=1.0)
        return float(sat.T - 273.15)

    @staticmethod
    def criticalPressure() -> float:
        return float(IAPWS95.Pc * 10.0)

    @staticmethod
    def criticalTemperatur() -> float:
        return float(IAPWS95.Tc - 273.15)

    @staticmethod
    def hV_p(p_bar: float) -> float:
        p_mpa = p_bar / 10.0
        sat = IAPWS95(P=p_mpa, x=1.0)
        return float(sat.h)

    @staticmethod
    def hL_p(p_bar: float) -> float:
        p_mpa = p_bar / 10.0
        sat = IAPWS95(P=p_mpa, x=0.0)
        return float(sat.h)

    @staticmethod
    def h_pt(p_bar: float, t_c: float) -> float:
        p_mpa = p_bar / 10.0
        t_k = t_c + 273.15
        state = IAPWS95(P=p_mpa, T=t_k)
        return float(state.h)


# 实例化 IAPWS-95 物性计算器（保持 _xsteam 引用名称以兼容原有测试与模块调用）
_xsteam = _IAPWS95Adapter()


def _validate_steam_state(inputs: dict) -> None:
    pressure, temperature = inputs["steam_pressure"], inputs["steam_temperature"]
    # 临界点以上按单相流体处理；低于临界压力时必须处于汽相侧。
    minimum = _xsteam.tsat_p(pressure * 10.0) if pressure * 10.0 < _xsteam.criticalPressure() else _xsteam.criticalTemperatur()
    if temperature < minimum - 1e-4:
        raise ValueError("蒸汽温度低于该绝对压力的汽相边界，请核对绝压与温度")


def _validate_water_state(inputs: dict) -> None:
    pressure, temperature = inputs["feedwater_pressure"], inputs["feedwater_temperature"]
    if pressure * 10.0 < _xsteam.criticalPressure() and temperature >= _xsteam.tsat_p(pressure * 10.0) - 1e-4:
        raise ValueError("给水必须处于液相区，请核对绝对压力与温度")


def _calc_steam_enthalpy(inputs: dict) -> dict:
    p_mpa = inputs["steam_pressure"]
    t_c = inputs["steam_temperature"]
    p_bar = p_mpa * 10.0
    if p_bar < _xsteam.criticalPressure() and abs(t_c - _xsteam.tsat_p(p_bar)) <= 0.01:
        h_kj_kg = float(_xsteam.hV_p(p_bar))
    else:
        h_kj_kg = float(_xsteam.h_pt(p_bar, t_c))
    return {"steam_enthalpy": h_kj_kg}

# ================= 1. 蒸汽焓值查表计算 =================
# 公式：根据 (蒸汽工作压力, 蒸汽工作温度) 查IAPWS水蒸气物性表 = 蒸汽比焓
steam_enthalpy_formula = EmpiricalFormula(
    metadata=FormulaMetadata(
        id="thermal.steam_enthalpy",
        name="蒸汽焓值查表计算",
        category="thermal",
        description="基于 IAPWS-95 国际水蒸气热力学科学基准状态方程，根据蒸汽工作压力与温度确定过热/饱和蒸汽比焓值。",
        notes="输入压力必须换算为绝对工作压力；若为湿饱和蒸汽需关注干度，目前默认过热或饱和单相蒸汽区。",
        formula_type=FormulaType.EMPIRICAL,
        inputs=[
            Pin(
                name="steam_pressure",
                unit="MPa",
                description="蒸汽绝对工作压力（MPa）",
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
    validator=_validate_steam_state,
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
        description="基于 IAPWS-95 国际水蒸气热力学科学基准状态方程，根据锅炉给水压力与给水温度计算给水初始比焓值。",
        notes="给水通常为过冷未饱和水，压力对水比焓影响较小，温度为主要决定因素。",
        formula_type=FormulaType.EMPIRICAL,
        inputs=[
            Pin(
                name="feedwater_pressure",
                unit="MPa",
                description="给水绝对压力（MPa）",
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
    validator=_validate_water_state,
)

# 自动注册
default_formula_registry.register(steam_enthalpy_formula)
default_formula_registry.register(water_enthalpy_formula)
