import abc
import logging
import requests
from typing import List, Optional

from openrecall.shared.config import settings

logger = logging.getLogger(__name__)

class BaseReranker(abc.ABC):
    @abc.abstractmethod
    def compute_score(self, query: str, documents: List[str]) -> List[float]:
        """Compute relevance scores for a list of documents against a query."""
        pass

class APIReranker(BaseReranker):
    def __init__(self):
        # Determine API URL
        self.api_url = settings.reranker_url
        
        # If user explicitly configured AI_API_BASE and we are using default/localhost reranker URL,
        # we try to infer the remote rerank endpoint.
        # Logic: If reranker_url is still default localhost AND ai_api_base is set, use ai_api_base
        if "localhost" in self.api_url and settings.ai_api_base:
            base = settings.ai_api_base.rstrip("/")
            self.api_url = f"{base}/rerank"
            
        # Use specific Reranker API Key if available, else fallback to global AI Key
        self.api_key = settings.reranker_api_key or settings.ai_api_key
        self.model = settings.reranker_model
        logger.info(f"Initialized APIReranker with URL: {self.api_url}")

    def compute_score(self, query: str, documents: List[str]) -> List[float]:
        if not documents:
            return []
        
        try:
            # Prepare Headers (Authorization)
            headers = {
                "Content-Type": "application/json"
            }
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            # Prepare Payload (OpenAI-compatible Rerank format)
            # Standard: { "model": "...", "query": "...", "documents": [...] }
            # TEI Legacy: { "query": "...", "texts": [...] }
            # We support both via simple heuristic or just send both fields to be safe if the provider is lenient,
            # but strictly speaking we should stick to one. 
            # Given the user pointed to AI_API_BASE (ModelScope/SiliconFlow), we use the "model" + "documents" format.
            
            payload = {
                "model": self.model,
                "query": query,
                "documents": documents,
                "top_n": len(documents) # Return scores for all
            }
            
            response = requests.post(self.api_url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # Parse Response
            # OpenAI format: { "results": [ {"index": 0, "relevance_score": 0.9}, ... ] }
            if isinstance(data, dict) and "results" in data:
                results = data["results"]
                # Sort by index to ensure order matches input documents
                results.sort(key=lambda x: x.get("index", 0))
                return [float(r.get("relevance_score", 0.0)) for r in results]
                
            # Fallback: TEI/BGE format (list of floats or dict with scores)
            elif isinstance(data, list):
                return [float(x) for x in data]
            elif isinstance(data, dict) and "scores" in data:
                return [float(x) for x in data["scores"]]
            else:
                logger.error(f"Unexpected API response format: {data}")
                return [0.0] * len(documents)
                
        except Exception as e:
            logger.error(f"Reranker API failed: {e}")
            return [0.0] * len(documents)

class LocalReranker(BaseReranker):
    def __init__(self):
        self.model_name = settings.reranker_model
        self.model = None
        self.tokenizer = None
        self.device = self._get_device()
        logger.info(f"Initialized LocalReranker (Lazy Loading) with model: {self.model_name} on {self.device}")

    def _get_device(self):
        import torch
        if settings.device != "cpu":
            return settings.device
        
        if torch.cuda.is_available():
            return "cuda"
        elif torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    def _load_model(self):
        if self.model is not None:
            return

        logger.info(f"Loading Reranker model: {self.model_name}...")
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name, trust_remote_code=True)
            self.model = AutoModelForSequenceClassification.from_pretrained(
                self.model_name, 
                trust_remote_code=True,
                torch_dtype=torch.float16 if self.device != "cpu" else torch.float32
            ).to(self.device)
            self.model.eval()
            logger.info("Reranker model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load local reranker model: {e}")
            raise

    def compute_score(self, query: str, documents: List[str]) -> List[float]:
        if not documents:
            return []
            
        try:
            self._load_model()
            
            import torch
            # Construct pairs
            pairs = [[query, doc] for doc in documents]
            
            with torch.no_grad():
                # Qwen-Reranker supports long context (32k), so we use a large max_length
                inputs = self.tokenizer(
                    pairs, 
                    padding=True, 
                    truncation=True, 
                    return_tensors='pt',
                    max_length=32768 
                ).to(self.device)
                
                outputs = self.model(**inputs, return_dict=True)
                # Some rerankers output a single logit, others might be classification
                # Assuming standard SequenceClassification for reranking (1 output neuron or logits[0])
                scores = outputs.logits.view(-1).float()
                
                return scores.cpu().numpy().tolist()
                
        except Exception as e:
            logger.error(f"Local reranking failed: {e}")
            return [0.0] * len(documents)

def get_reranker() -> BaseReranker:
    if settings.reranker_mode == "local":
        return LocalReranker()
    return APIReranker()
