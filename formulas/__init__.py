"""
Formulas package exports and automatic registration.
"""

# 导入各子模块以触发公式向 default_formula_registry 自动注册
import formulas.thermal.water_steam_properties  # noqa: F401
import formulas.thermal.energy_balance  # noqa: F401
import formulas.operation.operating_economics  # noqa: F401
import formulas.sizing.equipment_sizing  # noqa: F401
from core.formula import default_formula_registry

__all__ = ["default_formula_registry"]
