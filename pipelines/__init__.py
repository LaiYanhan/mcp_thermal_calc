"""
Pipelines package exports and automatic registration.
"""

import pipelines.valley_molten_salt_steam  # noqa: F401
from core.pipeline import pipeline_registry

__all__ = ["pipeline_registry"]
