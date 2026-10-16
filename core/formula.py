"""
Formula engine: algebraic bidirectional solver with SymPy and empirical black-box functions.
"""

from abc import ABC, abstractmethod
import ast
import math
import re
from copy import deepcopy
from dataclasses import asdict
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import sympy as sp
from core.types import FormulaMetadata, FormulaType, Pin
from core.storage import data_directory, read_json, write_json, synchronized


def parse_math_expression(expression: str):
    """将受限数学语法逐节点构造为 SymPy 对象，禁止 eval/parse_expr。"""
    if len(expression) > 2000:
        raise ValueError("公式过长")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as error:
        raise ValueError("公式语法错误，请使用变量标识和数学运算") from error
    if len(list(ast.walk(tree))) > 150:
        raise ValueError("公式过于复杂，请拆分为原子算子")
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            if any(isinstance(child, ast.Pow) for child in ast.walk(node.left)):
                raise ValueError("不支持嵌套幂运算，请拆分公式")
            exponent = node.right.operand if isinstance(node.right, ast.UnaryOp) else node.right
            if not isinstance(exponent, ast.Constant):
                raise ValueError("指数必须为数值常量")

    def convert(node):
        if isinstance(node, ast.Name) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", node.id):
            return sp.Symbol(node.id)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            if not math.isfinite(node.value) or abs(node.value) > 1e12:
                raise ValueError("公式数值超出允许范围")
            return sp.Rational(str(node.value))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = convert(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp):
            left, right = convert(node.left), convert(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                if right == 0:
                    raise ValueError("公式不能除以零")
                return left / right
            if isinstance(node.op, ast.Pow) and right.is_number and abs(float(right)) <= 12:
                return left ** right
        raise ValueError("公式仅支持变量、数值及 + - * / **，不允许函数调用或属性访问")

    return convert(tree.body)


class BaseFormula(ABC):
    """
    原子公式基类
    """
    def __init__(self, metadata: FormulaMetadata):
        self.metadata = metadata
        self.input_pins = {p.name: p for p in metadata.inputs}
        self.output_pins = {p.name: p for p in metadata.outputs}

    def validate_inputs(self, inputs: Dict[str, float]) -> None:
        if set(inputs) != set(self.input_pins):
            raise ValueError(f"算子 {self.metadata.id} 的输入引脚不完整或包含未知引脚")
        for name, pin in self.input_pins.items():
            pin.validate(inputs[name])

    def pin_contract(self, solve_target=None):
        """返回节点当前方向的已知量和待求量；查表算子保持固定方向。"""
        if solve_target is not None:
            raise ValueError("物性/查表算子不支持配置待求参数")
        return self.input_pins, self.output_pins

    def validate_knowns(self, inputs, solve_target=None):
        self.pin_contract(solve_target)
        self.validate_inputs(inputs)

    def execute_for_target(self, inputs, solve_target=None):
        self.pin_contract(solve_target)
        return self.execute(inputs)

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
        if equation_str.count("=") == 1:
            lhs_str, rhs_str = equation_str.split("=", 1)
            lhs_expr = parse_math_expression(lhs_str)
            rhs_expr = parse_math_expression(rhs_str)
            self.sympy_eq = sp.Eq(lhs_expr, rhs_expr, evaluate=False)
        else:
            raise ValueError("代数公式必须包含一个等号")

        # 收集方程中所有符号
        self.all_symbols = {str(s): s for s in self.sympy_eq.free_symbols}
        pins = metadata.inputs + metadata.outputs
        if not metadata.inputs or not metadata.outputs or len({p.name for p in pins}) != len(pins):
            raise ValueError("算子必须有不重复的输入与输出引脚")
        if set(self.all_symbols) != {p.name for p in pins}:
            raise ValueError("方程中的变量必须与输入、输出引脚完全一致")
        if len(self.all_symbols) > 20:
            raise ValueError("单个原子算子的变量不能超过 20 个")
        self.metadata.expression = equation_str
        self.metadata.is_bidirectional = True
        self._solutions = {}
        if len(metadata.outputs) != 1:
            raise ValueError("单个代数方程必须声明一个可唯一求解的输出")
        output = metadata.outputs[0].name
        solutions = sp.solve(self.sympy_eq, self.all_symbols[output])
        if len(solutions) != 1:
            raise ValueError("代数方程的正向输出必须存在唯一解析解")
        self._solutions[output] = solutions

    def pin_contract(self, solve_target=None):
        target = self.metadata.outputs[0].name if solve_target is None else solve_target
        pins = {**self.input_pins, **self.output_pins}
        if target not in pins:
            raise ValueError(f"未声明的待求参数：{target}")
        if target not in self._solutions:
            self._solutions[target] = sp.solve(self.sympy_eq, self.all_symbols[target])
        if len(self._solutions[target]) != 1:
            raise ValueError(f"参数 {target} 没有唯一解析解")
        return {name: pin for name, pin in pins.items() if name != target}, {target: pins[target]}

    def validate_knowns(self, inputs, solve_target=None):
        known_pins, _ = self.pin_contract(solve_target)
        if set(inputs) != set(known_pins):
            raise ValueError("必须提供待求参数之外的全部已知变量")
        for name, pin in known_pins.items():
            pin.validate(inputs[name])

    def execute_for_target(self, inputs, solve_target=None):
        self.validate_knowns(inputs, solve_target)
        _, outputs = self.pin_contract(solve_target)
        return {target: self.solve(inputs, target) for target in outputs}

    def display_expression(self, target):
        """中文仅用于展示；求解仍使用符号方程和稳定变量标识。"""
        self.pin_contract(target)
        expression = self.equation_str if target == self.metadata.outputs[0].name else f"{target} = {sp.sstr(self._solutions[target][0])}"
        expression = expression.replace("**", "^").replace("*", " × ").replace("/", " ÷ ")
        pins = {**self.input_pins, **self.output_pins}
        return re.sub(r"[A-Za-z][A-Za-z0-9_]*", lambda match: pins[match[0]].description if match[0] in pins else match[0], expression)

    def execute(self, inputs: Dict[str, float]) -> Dict[str, float]:
        """正向执行，计算所有 outputs 中的引脚"""
        self.validate_inputs(inputs)

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

        pins = {**self.input_pins, **self.output_pins}
        if target in knowns or set(knowns) - set(pins):
            raise ValueError("已知变量不能包含目标变量或未声明的引脚")
        for name, value in knowns.items():
            pins[name].validate(value)

        target_sym = self.all_symbols[target]
        # 解析解求 target
        if target not in self._solutions:
            self._solutions[target] = sp.solve(self.sympy_eq, target_sym)
        solutions = self._solutions[target]
        if not solutions:
            raise ValueError(f"方程 '{self.equation_str}' 无法解析求解未知数 '{target}'")
        if len(solutions) != 1:
            raise ValueError("方程存在多个解析根，不能自动选择结果")

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

        # 先代入再数值化，避免零温差被高精度 evalf 近似为极小非零数。
        evaluated = sol_expr.subs(subs_dict)
        if evaluated.is_real is not True or evaluated.is_finite is not True:
            raise ValueError(f"求解 {target} 得到非有限实数，请检查除数和物理边界")
        eval_val = float(evaluated)
        pins[target].validate(eval_val)
        return eval_val


class EmpiricalFormula(BaseFormula):
    """
    经验公式 / 物性黑盒函数 / 离散查表选型
    """
    def __init__(self, metadata: FormulaMetadata, func: Callable[[Dict[str, float]], Dict[str, float]], validator=None):
        super().__init__(metadata)
        self.func = func
        self.validator = validator
        self.metadata.formula_type = FormulaType.EMPIRICAL
        self.metadata.is_bidirectional = False

    def validate_inputs(self, inputs: Dict[str, float]) -> None:
        super().validate_inputs(inputs)
        if self.validator:
            self.validator(inputs)

    def execute(self, inputs: Dict[str, float]) -> Dict[str, float]:
        self.validate_inputs(inputs)

        results = self.func(inputs)

        if set(results) != set(self.output_pins):
            raise ValueError(f"算子 {self.metadata.id} 未返回完整的声明输出")

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
            raise ValueError(f"算子 {fid} 已存在，请使用原地修改")
        self._formulas[fid] = formula

    @synchronized
    def save_operator(self, data: Dict[str, Any], update: bool = False) -> BaseFormula:
        """先构造并验证完整候选对象，落盘成功后再原地替换注册项。"""
        fid = data.get("operator_id") if update else data.get("id")
        if not isinstance(fid, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.]*", fid):
            raise ValueError("算子 ID 格式不正确")
        if not update and fid in self._formulas:
            raise ValueError(f"算子 {fid} 已存在，请使用原地修改")
        original = self.get(fid) if update else None
        equation = data.get("formula", data.get("equation"))
        if original:
            metadata = deepcopy(original.metadata)
            for key in ("name", "description", "notes"):
                if key in data:
                    setattr(metadata, key, data[key])
            if not isinstance(original, AlgebraicFormula):
                if equation and equation != metadata.expression:
                    raise ValueError("物性/查表算子不支持代数公式编辑")
                candidate = EmpiricalFormula(metadata, original.func, original.validator)
            else:
                candidate = AlgebraicFormula(metadata, equation or original.equation_str)
        else:
            if not data.get("inputs") or not data.get("outputs"):
                raise ValueError("新增算子必须明确输入、输出引脚及其单位")
            metadata = FormulaMetadata(
                id=fid, name=data.get("name", ""), category=data.get("category", "custom"),
                description=data.get("description", ""), notes=data.get("notes", ""),
                formula_type=FormulaType.ALGEBRAIC,
                inputs=[Pin(**p) for p in data["inputs"]],
                outputs=[Pin(**p) for p in data["outputs"]],
            )
            candidate = AlgebraicFormula(metadata, equation or "")
        if not isinstance(candidate.metadata.name, str) or not candidate.metadata.name.strip():
            raise ValueError("算子名称不能为空")
        stored = read_json(data_directory() / "operators.json", {})
        stored[fid] = asdict(candidate.metadata)
        write_json(data_directory() / "operators.json", stored)
        self._formulas[fid] = candidate
        return candidate

    @synchronized
    def load_saved(self) -> None:
        for fid, data in read_json(data_directory() / "operators.json", {}).items():
            metadata = FormulaMetadata(**{**data,
                "formula_type": FormulaType(data["formula_type"]),
                "inputs": [Pin(**p) for p in data["inputs"]],
                "outputs": [Pin(**p) for p in data["outputs"]],
            })
            if metadata.formula_type == FormulaType.ALGEBRAIC:
                self._formulas[fid] = AlgebraicFormula(metadata, metadata.expression)
            else:
                original = self.get(fid)
                self._formulas[fid] = EmpiricalFormula(metadata, original.func, original.validator)

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
                "variables": [asdict(pin) for pin in meta.inputs + meta.outputs],
                "default_target": meta.outputs[0].name if isinstance(f, AlgebraicFormula) else None,
                "solve_targets": [],
                "display_expressions": {},
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
            if isinstance(f, AlgebraicFormula):
                for pin in meta.inputs + meta.outputs:
                    try:
                        item["display_expressions"][pin.name] = f.display_expression(pin.name)
                        item["solve_targets"].append(pin.name)
                    except ValueError:
                        continue
            catalog.append(item)
        return catalog

registry = FormulaRegistry()
default_formula_registry = registry
