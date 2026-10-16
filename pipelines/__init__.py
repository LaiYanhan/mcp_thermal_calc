"""
Pipelines package exports and automatic registration.
"""

import pipelines.valley_molten_salt_steam  # noqa: F401
from core.pipeline import pipeline_registry

pipeline_registry.load_saved()

__all__ = ["pipeline_registry"]
