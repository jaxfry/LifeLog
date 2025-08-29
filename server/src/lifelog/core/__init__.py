from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # This tells pydantic to load variables from a .env file if it exists,
    # which is great for local development outside of Docker.
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    # Database Configuration
    DATABASE_URL: str

    # Application Configuration
    APP_ENV: str = "development"
    SECRET_KEY: str

# Create a single, immutable instance of the settings
settings = Settings()