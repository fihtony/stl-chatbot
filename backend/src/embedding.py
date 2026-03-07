"""Embedding client using sentence-transformers or TF-IDF fallback."""

import time
import os
import pickle
from pathlib import Path
from typing import List, Optional
import numpy as np

# Allow loading HuggingFace/sentence-transformers cached models that contain custom
# classes (PyTorch 2.4+ enforces weights_only=True by default; cached models need False).
# Only applied when weights_only is not explicitly passed at the call site.
# See: https://pytorch.org/docs/stable/notes/serialization.html
if "TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD" not in os.environ:
    os.environ["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] = "1"

# Try to import sentence-transformers, fall back to TF-IDF if unavailable
SENTENCE_TRANSFORMERS_AVAILABLE = False
try:
    from sentence_transformers import SentenceTransformer

    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    pass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class TfidfEmbedder:
    """Fallback TF-IDF based embedder when neural models unavailable."""

    def __init__(
        self, embedding_dim: int = 768, cache_path: str = "./data/tfidf_vectorizer.pkl"
    ):
        self.cache_path = Path(cache_path)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.embedding_dim = embedding_dim
        self._fitted = False

        # Try to load cached vectorizer
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "rb") as f:
                    self.vectorizer = pickle.load(f)
                    self._fitted = True
                    print(f"   Loaded cached TF-IDF vectorizer from {self.cache_path}")
            except Exception as e:
                print(f"   Warning: Could not load cached vectorizer: {e}")
                self._init_new_vectorizer()
        else:
            self._init_new_vectorizer()

    def _init_new_vectorizer(self):
        self.vectorizer = TfidfVectorizer(
            max_features=self.embedding_dim,
            ngram_range=(1, 2),
            sublinear_tf=True,
        )
        self._fitted = False

    def fit(self, texts: List[str]):
        """Fit the vectorizer on texts and save to cache."""
        self.vectorizer.fit(texts)
        self._fitted = True

        # Save to cache
        try:
            with open(self.cache_path, "wb") as f:
                pickle.dump(self.vectorizer, f)
            print(f"   Saved TF-IDF vectorizer to {self.cache_path}")
        except Exception as e:
            print(f"   Warning: Could not save vectorizer: {e}")

    def transform(self, texts: List[str]) -> np.ndarray:
        """Transform texts to vectors."""
        if not self._fitted:
            raise ValueError(
                "TF-IDF vectorizer not fitted. Please run 'index' command first."
            )

        sparse_matrix = self.vectorizer.transform(texts)

        # Convert to dense and pad/truncate to fixed dimension
        dense = sparse_matrix.toarray()

        # Pad or truncate to target dimension
        actual_dim = dense.shape[1]
        if actual_dim < self.embedding_dim:
            padded = np.zeros((dense.shape[0], self.embedding_dim))
            padded[:, :actual_dim] = dense
            dense = padded
        elif actual_dim > self.embedding_dim:
            dense = dense[:, : self.embedding_dim]

        # Normalize
        norms = np.linalg.norm(dense, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        dense = dense / norms

        return dense


class EmbeddingClient:
    """Client for generating embeddings using multilingual models or TF-IDF fallback."""

    def __init__(
        self, model_name: str = "intfloat/multilingual-e5-base", device: str = "cpu"
    ):
        """
        Initialize the embedding client.

        Args:
            model_name: HuggingFace model name
            device: 'cpu' or 'cuda'
        """
        self.model_name = model_name
        self.device = device
        self._model: Optional[SentenceTransformer] = None
        self._tfidf: Optional[TfidfEmbedder] = None
        self._use_tfidf = False
        self._embedding_dim = 768  # Default dimension

        # Detect if this is an E5 model (requires query: / passage: prefixes)
        self._is_e5_model = "e5" in model_name.lower()
        # BGE-M3 and other BGE models don't use prefixes
        self._is_bge_model = "bge" in model_name.lower()

    @property
    def model(self):
        """Lazy load the model, falling back to TF-IDF if fails."""
        if self._model is None and not self._use_tfidf:
            if SENTENCE_TRANSFORMERS_AVAILABLE:
                try:
                    # Try to load with SSL workaround
                    import ssl
                    import httpx

                    # Patch httpx for SSL issues
                    original_client = httpx.Client

                    def patched_client(*args, **kwargs):
                        kwargs["verify"] = False
                        return original_client(*args, **kwargs)

                    httpx.Client = patched_client

                    ssl._create_default_https_context = ssl._create_unverified_context

                    self._model = SentenceTransformer(
                        self.model_name, device=self.device
                    )
                    self._embedding_dim = self._model.get_sentence_embedding_dimension()
                    print(f"✅ Loaded neural embedding model: {self.model_name}")
                except Exception as e:
                    print(f"⚠️  Could not load neural model ({e})")
                    print(
                        "   Falling back to TF-IDF embeddings (limited cross-language support)"
                    )
                    self._use_tfidf = True
            else:
                print("⚠️  sentence-transformers not available, using TF-IDF fallback")
                self._use_tfidf = True

        if self._use_tfidf and self._tfidf is None:
            self._tfidf = TfidfEmbedder(embedding_dim=self._embedding_dim)

        return self._model if not self._use_tfidf else None

    def embed_texts(
        self, texts: List[str], batch_size: int = 32, show_progress: bool = False
    ) -> np.ndarray:
        """
        Embed a list of texts.

        Args:
            texts: List of text strings
            batch_size: Batch size for encoding
            show_progress: Show progress bar

        Returns:
            numpy array of shape (n_texts, embedding_dim)
        """
        # Force model load
        _ = self.model

        if self._use_tfidf:
            # Use TF-IDF fallback
            self._tfidf.fit(texts)
            return self._tfidf.transform(texts)
        else:
            # Apply prefix based on model type
            # E5 models require "passage: " prefix for documents
            # BGE models don't use prefixes
            if self._is_e5_model:
                prefixed_texts = [f"passage: {t}" for t in texts]
            else:
                prefixed_texts = texts  # BGE and other models

            embeddings = self._model.encode(
                prefixed_texts,
                batch_size=batch_size,
                show_progress_bar=show_progress,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )

            return embeddings

    def embed_query(self, query: str) -> np.ndarray:
        """
        Embed a single query.

        Args:
            query: Query text

        Returns:
            numpy array of shape (embedding_dim,)
        """
        # Force model load
        _ = self.model

        if self._use_tfidf:
            # Use TF-IDF fallback
            embedding = self._tfidf.transform([query])
            return embedding[0]
        else:
            # Apply prefix based on model type
            # E5 models require "query: " prefix for queries
            # BGE models don't use prefixes
            if self._is_e5_model:
                prefixed_query = f"query: {query}"
            else:
                prefixed_query = query  # BGE and other models

            embedding = self._model.encode(
                prefixed_query,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )

            return embedding

    def embed_query_timed(self, query: str) -> tuple[np.ndarray, float]:
        """
        Embed a query and return the time taken.

        Returns:
            Tuple of (embedding, time_ms)
        """
        start = time.time()
        embedding = self.embed_query(query)
        elapsed_ms = (time.time() - start) * 1000
        return embedding, elapsed_ms

    @property
    def embedding_dim(self) -> int:
        """Get embedding dimension."""
        _ = self.model  # Force load
        return self._embedding_dim

    @property
    def is_neural(self) -> bool:
        """Check if using neural embeddings (vs TF-IDF fallback)."""
        _ = self.model
        return not self._use_tfidf
