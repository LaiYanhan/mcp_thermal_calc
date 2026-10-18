"""严格解析声明式 JSON；不支持 Python 模板。"""

import json

from core.definitions import PipelineDefinition, formula_definition_adapter
from core.pipeline import Pipeline


def parse_definition(source, kind: str):
    if isinstance(source, str):
        if len(source) > 50000:
            raise ValueError("定义过长")
        source = json.loads(source)
    if kind == "formula":
        return formula_definition_adapter.validate_python(source).model_dump()
    if kind == "pipeline":
        return Pipeline.from_dict(PipelineDefinition.model_validate(source).model_dump())
    raise ValueError("未知的 JSON 定义类型")
