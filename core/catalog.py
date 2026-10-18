"""服务启动时按依赖顺序扫描 JSON 公式和管道目录。"""

from core.formula import default_formula_registry
from core.pipeline import pipeline_registry

default_formula_registry.load_directory()
pipeline_registry.load_directory()
