"""contexta.knowledge — KnowledgeMemory subsystem.

Exports KnowledgeContext and KnowledgeMemoryService for use by pipeline
components (DimensionRunner, ArbitratorEngine, LayerTwoArbitrator, Advisor).
"""

from .memory import KnowledgeContext, KnowledgeMemoryService

__all__ = ["KnowledgeContext", "KnowledgeMemoryService"]
