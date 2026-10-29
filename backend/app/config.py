from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AIDriveAltium"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/aidrive_altium"
    secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = 7
    credential_encryption_key: str = ""
    outbound_allowed_urls: list[str] = ["https://api.openai.com/v1", "https://api.anthropic.com"]

    admin_email: str = "admin@example.com"
    admin_password: str = ""
    admin_bootstrap_reset_password: bool = False

    def validate_security(self) -> None:
        if not self.secret_key.strip() or self.secret_key in {"dev-secret-change-me-in-production", "change-me-in-production"}:
            raise RuntimeError("Set a non-default SECRET_KEY before startup")

    def validate_bootstrap_password(self) -> None:
        if not self.admin_password.strip() or self.admin_password == "admin123456":
            raise RuntimeError("Set a non-default ADMIN_PASSWORD for admin creation or reset")

    data_dir: Path = Path("./data")
    parse_worker_enabled: bool = True
    parse_poll_seconds: float = 2.0

    # ===== AI 平台：模型配置 =====
    # API Key 加密密钥；留空时由 secret_key 经 SHA-256 派生（无需额外配置）
    ai_secret_key: str = ""
    # 模型配置写操作是否限管理员
    ai_config_write_admin_only: bool = True
    # 连接测试超时（秒）
    ai_model_test_timeout: float = 8.0
    # 是否允许本地/私网地址（ollama / llama.cpp 必需）
    ai_allow_private_model_hosts: bool = True
    # 默认采样参数（新建模型时的兜底）
    ai_default_temperature: float = 0.4
    ai_default_max_tokens: int = 4096

    # 与运行中 Altium 的实时连接（第二步启用）
    gateway_url: str = "http://localhost:3296"

    def resolve_data_dir(self) -> Path:
        path = self.data_dir if self.data_dir.is_absolute() else Path(__file__).resolve().parent.parent / self.data_dir
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
