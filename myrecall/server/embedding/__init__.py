"""Frame embedding module for multimodal vector search."""
from myrecall.server.embedding.models import FrameEmbedding
from myrecall.server.embedding.service import EmbeddingService
from myrecall.server.embedding.worker import EmbeddingWorker

__all__ = [
    "FrameEmbedding",
    "EmbeddingService",
    "EmbeddingWorker",
]
