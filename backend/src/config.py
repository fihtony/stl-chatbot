"""Configuration management for the chatbot."""

import os
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv


def _normalize_model_name(model: str) -> str:
    """Normalize model name to uppercase API format for ZhipuAI coding endpoint."""
    # Keep hyphens, just uppercase
    model_upper = model.upper()
    # Handle GLM models - use uppercase format
    if "GLM" in model_upper:
        # Specific model mappings (must match before generic processing)
        if "GLM-4.7" in model_upper or "GLM47" in model_upper:
            return "GLM-4.7"
        elif "GLM-4-FLASH" in model_upper or "GLMFLASH" in model_upper:
            return "GLM-4-FLASH"
        elif "GLM-4-PLUS" in model_upper or "GLMPLUS" in model_upper:
            return "GLM-4-PLUS"
        elif "GLM-4.5" in model_upper or "GLM45" in model_upper:
            # GLM-4.5 models
            if "AIR" in model_upper:
                return "GLM-4.5-AIR"
            else:
                return "GLM-4.5"
        elif "GLM-4.6" in model_upper or "GLM46" in model_upper:
            return "GLM-4.6"
        elif "GLM-5" in model_upper or "GLM5" in model_upper:
            return "GLM-5"
        # For other GLM models, ensure uppercase and proper hyphens
        return model_upper.replace("_", "-")
    # For non-GLM models, return as-is (could be OpenAI, etc.)
    return model


@dataclass
class Config:
    """Application configuration - Milvus only."""

    # ============================================================
    # AI Configuration - MUST be set in .env file
    # ============================================================
    ai_provider: str = ""
    ai_base_url: str = ""
    ai_api_key: str = ""
    ai_model: str = ""

    # ============================================================
    # Milvus Vector Database Configuration
    # ============================================================
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_collection: str = "documents"

    # ============================================================
    # Embedding Configuration (BGE-M3 for Milvus)
    # ============================================================
    # BAAI/bge-m3: 1024 dimensions, excellent cross-lingual semantic search
    embedding_model: str = "BAAI/bge-m3"
    embedding_device: str = "cpu"

    # ============================================================
    # Document Processing
    # ============================================================
    documents_path: str = "./data/input"

    # ============================================================
    # RAG Configuration
    # ============================================================
    chunk_size: int = 1024
    chunk_overlap: int = 200
    top_k: int = 10

    @classmethod
    def load(cls) -> "Config":
        """Load configuration from environment variables."""
        load_dotenv()

        # Read AI configuration
        ai_provider = os.getenv("AI_PROVIDER")
        ai_base_url = os.getenv("AI_BASE_URL")
        ai_api_key = os.getenv("AI_API_KEY")
        ai_model = os.getenv("AI_MODEL")

        # Validate required AI configuration
        if not ai_provider:
            raise ValueError("AI_PROVIDER is required in .env file")
        if not ai_base_url:
            raise ValueError("AI_BASE_URL is required in .env file")
        if not ai_api_key:
            raise ValueError("AI_API_KEY is required in .env file")
        if not ai_model:
            raise ValueError("AI_MODEL is required in .env file")

        return cls(
            ai_provider=ai_provider,
            ai_base_url=ai_base_url,
            ai_api_key=ai_api_key,
            ai_model=_normalize_model_name(ai_model),
            # Milvus configuration
            milvus_host=os.getenv("MILVUS_HOST", "localhost"),
            milvus_port=int(os.getenv("MILVUS_PORT", "19530")),
            milvus_collection=os.getenv("MILVUS_COLLECTION", "documents"),
            # Embedding configuration
            embedding_model=os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3"),
            embedding_device=os.getenv("EMBEDDING_DEVICE", "cpu"),
            # Document processing
            documents_path=os.getenv("DOCUMENTS_PATH", "./data/input"),
            # RAG configuration
            chunk_size=int(os.getenv("CHUNK_SIZE", "1024")),
            chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "200")),
            top_k=int(os.getenv("TOP_K", "10")),
        )

    def get_milvus_connection(self) -> tuple[str, int]:
        """Get Milvus connection parameters."""
        return (self.milvus_host, self.milvus_port)

    def get_documents_path(self) -> Path:
        """Get absolute path to documents directory."""
        return Path(self.documents_path).resolve()


# Global config instance
config = Config.load()
