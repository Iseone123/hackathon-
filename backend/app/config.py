"""Конфигурация приложения из переменных окружения."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(_REPO_ROOT / ".env"), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Yandex AI Studio
    yc_api_key: str = ""
    yc_folder_id: str = ""

    # LLM
    llm_completion_url: str = (
        "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    )
    llm_embedding_url: str = (
        "https://llm.api.cloud.yandex.net/foundationModels/v1/textEmbedding"
    )
    yandexgpt_model: str = "yandexgpt"
    yandexgpt_lite_model: str = "yandexgpt-lite"
    embed_doc_model: str = "text-search-doc"
    embed_query_model: str = "text-search-query"
    llm_timeout_sec: float = 120.0
    llm_max_retries: int = 8
    llm_request_delay_sec: float = 3.0
    embed_parallel_workers: int = 4
    llm_temperature: float = 0.3
    llm_max_tokens: int = 4000

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "documents"

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "hypothesis_neo4j"

    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "hypothesis-data"
    minio_secure: bool = False

    # Paths (в Docker: /app/data, локально: <repo>/data)
    data_dir: str = "data"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # Security (локальное развёртывание с конфиденциальными данными)
    api_auth_enabled: bool = False
    # Формат: key:role,key2:role2 (роли: viewer | expert | admin)
    api_keys: str = ""
    encrypt_hypotheses_at_rest: bool = False
    # Fernet key: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    data_encryption_key: str = ""

    # RAG / generation
    chunk_size: int = 1200
    chunk_overlap: int = 200
    retrieval_top_k: int = 12
    retrieval_example_boost: float = 0.35
    retrieval_example_inject: int = 4
    agentic_rag_enabled: bool = True
    agentic_rag_max_steps: int = 5
    agentic_rag_step_top_k: int = 6
    generation_samples: int = 1
    default_hypothesis_count: int = 5
    min_hypothesis_count: int = 1
    max_hypothesis_count: int = 12
    judge_repair_passes: int = 1
    judge_min_output: int = 3
    judge_drop_below_objective: float = 0.40
    judge_min_approve_score: float = 6.5
    judge_snippet_overlap_min: float = 0.30
    judge_min_llm_testability: float = 6.0
    judge_min_llm_evidence: float = 6.0
    judge_min_llm_kpi_link: float = 5.5
    judge_min_llm_relevance: float = 6.0
    judge_issue_penalty: float = 0.55

    # Ranking weights (interpretable, configurable)
    weight_novelty: float = 0.30
    weight_feasibility: float = 0.25
    weight_expected_value: float = 0.30
    weight_risk: float = 0.15

    # Judge objective — метрика, которую максимизируем
    judge_objective_approval_weight: float = 0.55
    judge_objective_score_weight: float = 0.45
    judge_jqi_approval_weight: float = 0.50
    judge_jqi_score_weight: float = 0.35
    judge_jqi_grounding_weight: float = 0.15
    judge_quality_target: float = 75.0

    @property
    def data_dir_path(self) -> Path:
        p = Path(self.data_dir)
        if p.is_absolute():
            return p
        repo_data = Path(__file__).resolve().parent.parent.parent / "data"
        if repo_data.exists():
            return repo_data
        return Path.cwd() / self.data_dir

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir_path / "uploads"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir_path / "processed"

    @property
    def hypotheses_dir(self) -> Path:
        return self.data_dir_path / "hypotheses"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def model_uri(self, kind: str, model: str) -> str:
        prefix = "gpt" if kind == "gpt" else "emb"
        return f"{prefix}://{self.yc_folder_id}/{model}"

    def ranking_weights(self) -> dict[str, float]:
        return {
            "novelty": self.weight_novelty,
            "feasibility": self.weight_feasibility,
            "expected_value": self.weight_expected_value,
            "risk": self.weight_risk,
        }

    def llm_model_catalog(self) -> dict[str, str]:
        """Человекочитаемые названия моделей для UI и /health."""
        return {
            "generation": self.yandexgpt_model,
            "generation_label": "YandexGPT Pro 5",
            "judge": self.yandexgpt_lite_model,
            "judge_label": "YandexGPT Lite 5",
            "embed_doc": self.embed_doc_model,
            "embed_doc_label": "text-search-doc",
            "embed_query": self.embed_query_model,
            "embed_query_label": "text-search-query",
            "generation_samples": str(self.generation_samples),
        }


settings = Settings()
