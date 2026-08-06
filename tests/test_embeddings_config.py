from dataclasses import replace
import os
from unittest import TestCase
from unittest.mock import patch

from core.config import load_settings
from retrieval.embeddings import build_embeddings


class EmbeddingsConfigTests(TestCase):
    @patch.dict(os.environ, {"EMBEDDING_MODEL": "custom-local-model"})
    def test_load_settings_reads_embedding_model_from_env(self):
        settings = load_settings()

        self.assertEqual(settings.embedding_model, "custom-local-model")

    def test_openai_embedding_requires_api_key(self):
        settings = replace(
            load_settings(),
            embedding_model="text-embedding-3-small",
            openai_api_key=None,
        )

        with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
            build_embeddings(settings)

    @patch("retrieval.embeddings.MiniLMEmbeddings")
    def test_non_openai_model_uses_local_backend(self, mini_lm):
        sentinel = object()
        mini_lm.return_value = sentinel
        settings = replace(
            load_settings(),
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        )

        self.assertIs(build_embeddings(settings), sentinel)
        mini_lm.assert_called_once_with("sentence-transformers/all-MiniLM-L6-v2")
