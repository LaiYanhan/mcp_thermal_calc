"""解析人工审核后的声明式模板，只构造数据，不执行 Python 源码。"""

import ast
import json
import re
from dataclasses import asdict
from core.formula import AlgebraicFormula
from core.pipeline import Pipeline
from core.types import FormulaMetadata, FormulaType, Pin, PipelineStep, InputConstraint


def validate_filename(filename: str) -> None:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.py|\.json)?", filename):
        raise ValueError("文件名只能包含英文字母、数字和下划线，不允许目录或覆盖源文件")


def parse_definition(source: str, kind: str):
    """支持 JSON 定义及 Pin/FormulaMetadata/PipelineStep 构造式模板。"""
    if len(source) > 50000:
        raise ValueError("定义过长")
    try:
        data = json.loads(source)
    except json.JSONDecodeError:
        data = None
    if data is not None:
        if not isinstance(data, dict):
            raise ValueError("定义必须为 JSON 对象")
        return Pipeline.from_dict(data) if kind == "pipeline" else data

    tree = ast.parse(source)
    if len(list(ast.walk(tree))) > 4000:
        raise ValueError("定义过于复杂")
    constructors = {"Pin": Pin, "InputConstraint": InputConstraint, "FormulaMetadata": FormulaMetadata, "PipelineStep": PipelineStep,
                    "Pipeline": Pipeline, "AlgebraicFormula": AlgebraicFormula}
    imports = {"core.types": {"Pin", "InputConstraint", "FormulaMetadata", "FormulaType", "PipelineStep"},
               "core.formula": {"AlgebraicFormula", "default_formula_registry"},
               "core.pipeline": {"Pipeline", "PipelineStep", "pipeline_registry"}}
    values = {}
    registered = []

    def value(node):
        if isinstance(node, ast.Constant) and type(node.value) in (str, int, float, bool, type(None)):
            return node.value
        if isinstance(node, ast.Name) and node.id in values:
            return values[node.id]
        if isinstance(node, ast.List):
            return [value(item) for item in node.elts]
        if isinstance(node, ast.Dict) and all(key is not None for key in node.keys):
            return {value(key): value(item) for key, item in zip(node.keys, node.values)}
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant) and type(node.operand.value) in (int, float):
            return -node.operand.value
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "FormulaType" and node.attr == "ALGEBRAIC":
            return FormulaType.ALGEBRAIC
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in constructors and all(key.arg for key in node.keywords):
            return constructors[node.func.id](*[value(item) for item in node.args], **{key.arg: value(key.value) for key in node.keywords})
        raise ValueError("模板仅允许声明数据与白名单构造式，不允许执行函数、属性访问或动态代码")

    for statement in tree.body:
        if isinstance(statement, ast.ImportFrom):
            if statement.level or statement.module not in imports or any(name.name not in imports[statement.module] or name.asname for name in statement.names):
                raise ValueError("模板包含未允许的导入")
        elif isinstance(statement, ast.Assign) and len(statement.targets) == 1 and isinstance(statement.targets[0], ast.Name):
            values[statement.targets[0].id] = value(statement.value)
        elif isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant) and isinstance(statement.value.value, str):
            continue
        elif isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
            call = statement.value
            registry = "pipeline_registry" if kind == "pipeline" else "default_formula_registry"
            if not (isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name) and
                    call.func.value.id == registry and call.func.attr == "register" and len(call.args) == 1 and not call.keywords):
                raise ValueError("模板仅允许向指定注册表声明一个对象")
            registered.append(value(call.args[0]))
        else:
            raise ValueError("模板不允许函数定义、循环或动态执行")
    expected = Pipeline if kind == "pipeline" else AlgebraicFormula
    if len(registered) != 1 or not isinstance(registered[0], expected):
        raise ValueError("模板必须明确注册一个符合类型的对象")
    if kind == "pipeline":
        return registered[0]
    metadata = asdict(registered[0].metadata)
    return {**metadata, "equation": metadata["expression"]}
