"""Frame embedding module for multimodal vector search."""
from openrecall.server.embedding.models import FrameEmbedding
from openrecall.server.embedding.service import EmbeddingService
from openrecall.server.embedding.worker import EmbeddingWorker

__all__ = [
    "FrameEmbedding",
    "EmbeddingService",
    "EmbeddingWorker",
]
