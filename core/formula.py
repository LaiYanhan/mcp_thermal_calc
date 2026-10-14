"""
Formula engine: algebraic bidirectional solver with SymPy and empirical black-box functions.
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import sympy as sp
from core.types import FormulaMetadata, FormulaType, Pin


class BaseFormula(ABC):
    """
    原子公式基类
    """
    def __init__(self, metadata: FormulaMetadata):
        self.metadata = metadata
        self.input_pins = {p.name: p for p in metadata.inputs}
        self.output_pins = {p.name: p for p in metadata.outputs}

    @abstractmethod
    def execute(self, inputs: Dict[str, float]) -> Dict[str, float]:
        """正向计算所有输出引脚"""
        pass

    @abstractmethod
    def solve(self, knowns: Dict[str, float], target: str) -> float:
        """根据已知变量集合推导目标未知变量（支持逆向或正向求解）"""
        pass


class AlgebraicFormula(BaseFormula):
    """
    纯代数方程公式：基于 SymPy 实现自动正反向解析推导
    """
    def __init__(self, metadata: FormulaMetadata, equation_str: str):
        super().__init__(metadata)
        self.equation_str = equation_str
        # 方程格式如 "P_sgs = m_steam * delta_h / 3600"
        if "=" in equation_str:
            lhs_str, rhs_str = equation_str.split("=", 1)
            lhs_expr = sp.parse_expr(lhs_str.strip())
            rhs_expr = sp.parse_expr(rhs_str.strip())
            self.sympy_eq = sp.Eq(lhs_expr, rhs_expr)
        else:
            self.sympy_eq = sp.Eq(sp.parse_expr(equation_str.strip()), 0)

        # 收集方程中所有符号
        self.all_symbols = {str(s): s for s in self.sympy_eq.free_symbols}
        self.metadata.expression = equation_str
        self.metadata.is_bidirectional = True

    def execute(self, inputs: Dict[str, float]) -> Dict[str, float]:
        """正向执行，计算所有 outputs 中的引脚"""
        # 校验输入区间
        for name, pin in self.input_pins.items():
            if name in inputs:
                pin.validate(inputs[name])

        results = {}
        for out_pin in self.metadata.outputs:
            val = self.solve(inputs, out_pin.name)
            out_pin.validate(val)
            results[out_pin.name] = val
        return results

    def solve(self, knowns: Dict[str, float], target: str) -> float:
        """
        利用 SymPy 求解 target 未知数
        """
        if target not in self.all_symbols:
            raise KeyError(f"目标变量 '{target}' 不在该公式方程 '{self.equation_str}' 中")

        target_sym = self.all_symbols[target]
        # 解析解求 target
        solutions = sp.solve(self.sympy_eq, target_sym)
        if not solutions:
            raise RuntimeError(f"方程 '{self.equation_str}' 无法解析求解未知数 '{target}'")

        # 将已知数值替换进符号公式
        subs_dict = {}
        for sym_name, sym in self.all_symbols.items():
            if sym_name != target and sym_name in knowns:
                subs_dict[sym] = knowns[sym_name]

        # 检查是否所有依赖自由符号均已赋值
        sol_expr = solutions[0]
        needed_symbols = sol_expr.free_symbols
        for s in needed_symbols:
            if s not in subs_dict:
                raise ValueError(f"求解 '{target}' 缺少已知变量: '{str(s)}'（方程: {self.equation_str}）")

        eval_val = float(sol_expr.evalf(subs=subs_dict))
        return eval_val


class EmpiricalFormula(BaseFormula):
    """
    经验公式 / 物性黑盒函数 / 离散查表选型
    """
    def __init__(self, metadata: FormulaMetadata, func: Callable[[Dict[str, float]], Dict[str, float]]):
        super().__init__(metadata)
        self.func = func
        self.metadata.formula_type = FormulaType.EMPIRICAL
        self.metadata.is_bidirectional = False

    def execute(self, inputs: Dict[str, float]) -> Dict[str, float]:
        for name, pin in self.input_pins.items():
            if name in inputs:
                pin.validate(inputs[name])

        results = self.func(inputs)

        for name, val in results.items():
            if name in self.output_pins:
                self.output_pins[name].validate(val)
        return results

    def solve(self, knowns: Dict[str, float], target: str) -> float:
        """经验/查表函数默认不支持通用代数逆向求解"""
        if target in self.output_pins:
            res = self.execute(knowns)
            return res[target]
        raise NotImplementedError(
            f"经验/物性黑盒函数 '{self.metadata.id}' 属于不可解析逆推函数，仅支持正向查表求解出参，不支持逆推入参 '{target}'"
        )


class FormulaRegistry:
    """
    公式全局注册表
    """
    def __init__(self):
        self._formulas: Dict[str, BaseFormula] = {}

    def register(self, formula: BaseFormula) -> None:
        fid = formula.metadata.id
        if fid in self._formulas:
            # 允许更新注册
            pass
        self._formulas[fid] = formula

    def get(self, formula_id: str) -> BaseFormula:
        if formula_id not in self._formulas:
            raise KeyError(f"未注册的公式ID: '{formula_id}'. 请检查公式文件或注册表")
        return self._formulas[formula_id]

    def list_all(self) -> List[FormulaMetadata]:
        return [f.metadata for f in self._formulas.values()]

    def to_ai_catalog(self) -> List[Dict[str, Any]]:
        """输出供大模型（Agent）阅读理解的结构化公式说明清单"""
        catalog = []
        for f in self._formulas.values():
            meta = f.metadata
            item = {
                "id": meta.id,
                "name": meta.name,
                "category": meta.category,
                "description": meta.description,
                "notes": meta.notes,
                "type": meta.formula_type.value,
                "bidirectional": meta.is_bidirectional,
                "expression": meta.expression,
                "inputs": [
                    {
                        "name": p.name,
                        "unit": p.unit,
                        "description": p.description,
                        "min": p.min_value,
                        "max": p.max_value,
                        "default": p.default_value
                    }
                    for p in meta.inputs
                ],
                "outputs": [
                    {
                        "name": p.name,
                        "unit": p.unit,
                        "description": p.description
                    }
                    for p in meta.outputs
                ]
            }
            catalog.append(item)
        return catalog

registry = FormulaRegistry()
default_formula_registry = registry
