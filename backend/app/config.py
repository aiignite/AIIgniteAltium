from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AIDriveAltium"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/aidrive_altium"
    secret_key: str = "dev-secret-change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = 7

    admin_email: str = "admin@example.com"
    admin_password: str = "admin123456"
    admin_bootstrap_reset_password: bool = False

    data_dir: Path = Path("./data")

    # 与运行中 Altium 的实时连接（第二步启用）
    gateway_url: str = "http://localhost:3296"

    def resolve_data_dir(self) -> Path:
        path = self.data_dir if self.data_dir.is_absolute() else Path(__file__).resolve().parent.parent / self.data_dir
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
