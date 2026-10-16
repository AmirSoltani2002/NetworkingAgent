import math
import os
import threading

from .errors import ServiceError


class LocalEmbeddings:
    def __init__(self, settings):
        import torch
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding

        torch.set_num_threads(settings.torch_threads)
        settings.model_cache_dir.mkdir(parents=True, exist_ok=True)
        if settings.model_offline:
            os.environ["HF_HUB_OFFLINE"] = "1"
        self.settings = settings
        self.lock = threading.RLock()
        self.llama_model = HuggingFaceEmbedding(
            model_name=settings.embedding_model,
            revision=settings.embedding_revision,
            device=settings.embedding_device,
            cache_folder=str(settings.model_cache_dir),
            normalize=True,
            trust_remote_code=False,
            local_files_only=settings.model_offline,
            embed_batch_size=settings.embedding_batch_size,
        )
        self.tokenizer = self.llama_model._model.tokenizer
        self.max_tokens = min(settings.max_chunk_tokens, self.llama_model.max_length - 2)
        if (
            len(self.llama_model.get_text_embedding("Local embedding dimension check"))
            != settings.embedding_dimension
        ):
            raise RuntimeError("Local embedding dimension does not match RAG_EMBEDDING_DIMENSION")

    def token_count(self, text):
        return len(self.tokenizer.encode(text, add_special_tokens=False))

    def token_parts(self, text, max_tokens=None):
        limit = max_tokens or self.max_tokens
        offsets = self.tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)[
            "offset_mapping"
        ]
        result = []
        start = 0
        for i in range(0, len(offsets), limit):
            end = offsets[min(i + limit, len(offsets)) - 1][1]
            if i + limit >= len(offsets):
                end = len(text)
            result.append(text[start:end].strip())
            start = end
        return result or [text]

    def texts(self, texts):
        if not texts:
            return []
        with self.lock:
            try:
                groups = [self.token_parts(text) for text in texts]
                vectors = iter(
                    self.llama_model.get_text_embedding_batch([part for group in groups for part in group])
                )
                result = []
                for group in groups:
                    parts = [next(vectors) for _ in group]
                    mean = [sum(values) / len(parts) for values in zip(*parts)]
                    norm = math.sqrt(sum(value * value for value in mean))
                    if norm == 0 or not math.isfinite(norm):
                        raise ValueError("Invalid embedding")
                    result.append([value / norm for value in mean])
                return result
            except Exception:
                raise ServiceError(
                    503, "EMBEDDING_FAILED", "The local embedding model could not encode the input"
                ) from None

    def query(self, query):
        # Use the model's query prompt for instruction-trained embedding models.
        with self.lock:
            try:
                if self.token_count(query) > self.llama_model.max_length - 2:
                    raise ServiceError(
                        422, "QUERY_TOO_LONG", "Shorten the query to fit the embedding model token limit"
                    )
                return self.llama_model.get_query_embedding(query)
            except ServiceError:
                raise
            except Exception:
                raise ServiceError(
                    503, "EMBEDDING_FAILED", "The local embedding model could not encode the query"
                ) from None


class LocalReranker:
    def __init__(self, settings):
        from sentence_transformers import CrossEncoder

        if not settings.reranker_revision or settings.reranker_revision == "main":
            raise RuntimeError("Pin RAG_RERANKER_REVISION before enabling reranking")
        self.model = CrossEncoder(
            settings.reranker_model,
            revision=settings.reranker_revision,
            device=settings.embedding_device,
            trust_remote_code=False,
            cache_folder=str(settings.model_cache_dir),
            local_files_only=settings.model_offline,
        )
        self.lock = threading.Lock()

    def scores(self, query, passages):
        with self.lock:
            return [float(score) for score in self.model.predict([(query, passage) for passage in passages])]
