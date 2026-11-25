
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    DB_USER: str = ""
    DB_PASSWORD: str = ""
    DB_HOST: str = ""
    DB_PORT: int = 5432
    DB_NAME: str = ""

    # --- Active Directory (LDAP) ---
    # e.g. ldaps://dc01.empresa.local  (ldaps:// is strongly recommended: simple bind sends the password)
    LDAP_SERVER_URI: str = ""
    # UPN suffix used to bind as the user: "<username>@<LDAP_DOMAIN>"
    LDAP_DOMAIN: str = ""
    # Only accounts located in this OU (or any sub-OU) may log in, e.g. OU=TI,DC=empresa,DC=local
    LDAP_ALLOWED_OU_DN: str = ""
    LDAP_TIMEOUT_SECONDS: int = 5
    # Set to False only for a lab DC with a self-signed certificate
    LDAP_VALIDATE_CERT: bool = True

    # --- JWT issued after a successful AD login ---
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480

    # --- PowerShell scanner agents ---
    # Shared key the scanners send in the X-API-Key header. Empty = ingestion stays open (legacy mode).
    SCANNER_API_KEY: str = ""

    # Console log level for the "dxscan.*" loggers: DEBUG, INFO, WARNING or ERROR
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def missing_auth_settings(self) -> list[str]:
        """Returns the names of the auth settings that must be set before the API can start."""
        required = {
            "LDAP_SERVER_URI": self.LDAP_SERVER_URI,
            "LDAP_DOMAIN": self.LDAP_DOMAIN,
            "LDAP_ALLOWED_OU_DN": self.LDAP_ALLOWED_OU_DN,
        }
        missing = [name for name, value in required.items() if not value]
        if len(self.JWT_SECRET) < 32:
            missing.append("JWT_SECRET (minimum 32 characters)")
        return missing


settings = Settings()
