"""
Extended configuration for agent system
"""

import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings"""
    
    # ========== Basic Settings ==========
    APP_NAME: str = "PR Context Generator - AI Agent"
    VERSION: str = "2.0.0"
    DEBUG: bool = True
    ENVIRONMENT: str = "development"  # development, staging, production
    
    # ========== API Configuration ==========
    ALLOWED_ORIGINS: list = [
        "http://localhost:3000",
        "http://localhost:5173",
        "https://github.com",
        "chrome-extension://*",
    ]
    
    # Rate limiting
    RATE_LIMIT: str = "100"  # requests per minute
    
    # ========== LLM Configuration ==========
    GROQ_API_KEY: str = "your_groq_api_key_here"
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    
    # Optional: Additional LLM providers
    OPENAI_API_KEY: Optional[str] = None
    
    # ========== GitHub Integration ==========
    GITHUB_TOKEN: str = "your_github_token_here"
    GITHUB_WEBHOOK_SECRET: Optional[str] = None
    
    # ========== Agent System Configuration ==========
    MAX_CONCURRENT_AGENTS: int = 5
    AGENT_TIMEOUT_SECONDS: int = 600  # 10 minutes
    AGENT_MAX_ITERATIONS: int = 15
    
    # Agent behavior
    ENABLE_AUTO_APPROVE: bool = False  # Safety: disabled by default
    ENABLE_AUTO_FIX: bool = True  # Allow agents to create fix commits
    ENABLE_LEARNING: bool = True  # Enable memory learning
    
    # ========== Memory Configuration ==========
    MEMORY_STORAGE_PATH: str = "./data"
    
    # Optional: Redis for working memory (production)
    REDIS_URL: Optional[str] = None
    REDIS_TTL: int = 3600  # 1 hour
    
    # Optional: PostgreSQL for episodic memory (production)
    DATABASE_URL: Optional[str] = None
    
    # Optional: Vector database for semantic memory (production)
    PINECONE_API_KEY: Optional[str] = None
    PINECONE_ENVIRONMENT: Optional[str] = None
    PINECONE_INDEX: str = "agent-memory"
    
    WEAVIATE_URL: Optional[str] = None
    WEAVIATE_API_KEY: Optional[str] = None
    
    # ========== Task Queue Configuration ==========
    # Celery (for production async task processing)
    CELERY_BROKER_URL: Optional[str] = None  # e.g., redis://localhost:6379/0
    CELERY_RESULT_BACKEND: Optional[str] = None
    
    # ========== Monitoring & Observability ==========
    # Logging
    LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR
    LOG_FORMAT: str = "json"  # json or text
    
    # Sentry (error tracking)
    SENTRY_DSN: Optional[str] = None
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    
    # Prometheus (metrics)
    PROMETHEUS_ENABLED: bool = False
    PROMETHEUS_PORT: int = 9090
    
    # OpenTelemetry (distributed tracing)
    OTEL_ENABLED: bool = False
    OTEL_ENDPOINT: Optional[str] = None
    JAEGER_AGENT_HOST: Optional[str] = None
    JAEGER_AGENT_PORT: Optional[int] = None
    
    # ========== Cost Management ==========
    MAX_LLM_COST_PER_TASK: float = 1.0  # USD
    DAILY_LLM_BUDGET: float = 100.0  # USD
    ENABLE_COST_TRACKING: bool = True
    
    # ========== Security ==========
    API_KEY_HEADER: str = "X-API-Key"
    API_KEYS: list = []  # List of valid API keys for auth
    
    # JWT (if using token auth)
    JWT_SECRET_KEY: Optional[str] = None
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
