from __future__ import annotations

from functools import lru_cache

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings
from sentence_transformers import SentenceTransformer

from core.config import Settings


@lru_cache(maxsize=4)
def _load_model(model_name: str) -> SentenceTransformer:
    return SentenceTransformer(model_name)


class MiniLMEmbeddings(Embeddings):
    def __init__(self, model_name: str):
        self.model = _load_model(model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        embeddings = self.model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        embedding = self.model.encode([text], normalize_embeddings=True)
        return embedding[0].tolist()


def build_embeddings(settings: Settings) -> Embeddings:
    """Build the configured embedding client.

    OpenAI embedding models use the OpenAI API. Other model names are treated
    as Sentence Transformers model identifiers for backwards compatibility.
    """
    model_name = settings.embedding_model.strip()
    if not model_name:
        raise RuntimeError("EMBEDDING_MODEL must not be empty.")

    if model_name.startswith("text-embedding-"):
        if not settings.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is required when EMBEDDING_MODEL uses an OpenAI embedding model."
            )
        return OpenAIEmbeddings(model=model_name, api_key=settings.openai_api_key)

    return MiniLMEmbeddings(model_name)
