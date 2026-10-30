import logging
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("hydrasense.config")

# Known-insecure JWT secrets. The first entry was previously committed as the
# library default and must never be accepted outside local development; the
# second is the placeholder shipped in `.env.example`.
INSECURE_JWT_SECRETS = frozenset(
    {
        "hydrasense_super_secret_jwt_signing_key_32_bytes_min!",
        "replace_with_a_secure_secret_key_in_production",
        "changeme",
        "change-me",
        "secret",
        "your-256-bit-secret",
    }
)

MIN_JWT_SECRET_LENGTH = 32

# Environments that must never boot with a weak or missing JWT secret.
PRODUCTION_ENVS = frozenset({"production", "prod", "staging", "live"})

_SECRET_HINT = (
    "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\" "
    "and set it as JWT_SECRET_KEY in backend/.env (never commit it)."
)


class Settings(BaseSettings):
    APP_NAME: str = "HydraSense API"
    APP_ENV: str = "development"
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/hydrasense"
    # No default: a signing secret must come from the environment. Startup
    # fails (see validate_security) when it is missing, so a restart can never
    # silently mint a new key or fall back to a repository literal.
    JWT_SECRET_KEY: str | None = None
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    MQTT_BROKER_HOST: str = "localhost"
    MQTT_BROKER_PORT: int = 1883
    MQTT_TOPIC_PREFIX: str = "hydrasense/stations"
    # Broker authentication. Anonymous access is for local development only;
    # production startup refuses to run without a username and password.
    MQTT_USERNAME: str = ""
    MQTT_PASSWORD: str = ""
    MQTT_USE_TLS: bool = False
    MQTT_CA_CERT_PATH: str = ""
    MQTT_CLIENT_ID: str = "hydrasense-backend"
    # Explicit opt-in required to accept anonymous brokers in production.
    MQTT_ALLOW_ANONYMOUS: bool = False

    # --- CORS -------------------------------------------------------------
    # Comma-separated explicit origins. Empty means: development/preview
    # defaults in non-production environments, deny-all cross-origin in
    # production (set CORS_ALLOW_ORIGINS there before shipping a browser
    # client). "*" is rejected whenever credentials are enabled and in
    # production altogether.
    CORS_ALLOW_ORIGINS: str = ""
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: str = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
    CORS_ALLOW_HEADERS: str = "Authorization,Content-Type,Accept,X-Requested-With,Origin"

    # --- Rate limiting ----------------------------------------------------
    # Counters live in the rate_limit_counters table (shared by every API
    # worker through PostgreSQL), not in process memory.
    RATE_LIMIT_ENABLED: bool = True
    # Enable only behind a reverse proxy you control, so clients cannot spoof
    # X-Forwarded-For to dodge their own limits.
    RATE_LIMIT_TRUST_PROXY_HEADERS: bool = False
    RATE_LIMIT_LOGIN_MAX: int = 10
    RATE_LIMIT_LOGIN_WINDOW_SECONDS: int = 300
    RATE_LIMIT_REGISTER_MAX: int = 10
    RATE_LIMIT_REGISTER_WINDOW_SECONDS: int = 3600
    RATE_LIMIT_ACTIVATE_MAX: int = 10
    RATE_LIMIT_ACTIVATE_WINDOW_SECONDS: int = 3600

    # --- Notifications -------------------------------------------------------
    # Email is the only implemented channel; when SMTP_HOST is empty the
    # service records deliveries as "skipped_unconfigured" and logs instead -
    # it never breaks ingestion or alerting. SMTP credentials live only in .env.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "hydrasense@localhost"
    SMTP_USE_TLS: bool = True
    # Suppression window (seconds) for repeated notifications with the same
    # dedup key, and the maximum number of notifications per user per window.
    NOTIFICATION_COOLDOWN_SECONDS: int = 900
    NOTIFICATION_MAX_PER_WINDOW: int = 10

    # --- Public pages / QR ---------------------------------------------------
    # Origin of the public web application used for QR deep links. Local
    # development defaults to the Vite dev server; set this to the real public
    # origin before printing QR codes.
    PUBLIC_BASE_URL: str = "http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.strip().lower() in PRODUCTION_ENVS

    @property
    def jwt_secret(self) -> str:
        return (self.JWT_SECRET_KEY or "").strip()

    def validate_security(self) -> None:
        """Fail securely at application startup.

        Raises RuntimeError when a required secret is missing or, in a
        production-like environment, when it is short or a known insecure
        default. Never generates a replacement secret.
        """
        secret = self.jwt_secret
        fatal: list[str] = []

        if not secret:
            fatal.append(
                "JWT_SECRET_KEY is not configured; tokens cannot be signed "
                f"securely. {_SECRET_HINT}"
            )
        elif secret in INSECURE_JWT_SECRETS:
            message = (
                "JWT_SECRET_KEY is a known insecure default and must not be "
                f"used. {_SECRET_HINT}"
            )
            if self.is_production:
                fatal.append(message)
            else:
                logger.warning("%s (APP_ENV=%s keeps running)", message, self.APP_ENV)
        elif len(secret) < MIN_JWT_SECRET_LENGTH:
            message = (
                f"JWT_SECRET_KEY is shorter than {MIN_JWT_SECRET_LENGTH} characters. "
                f"{_SECRET_HINT}"
            )
            if self.is_production:
                fatal.append(message)
            else:
                logger.warning("%s (APP_ENV=%s keeps running)", message, self.APP_ENV)

        # MQTT: an anonymous broker lets anyone publish station telemetry, so
        # production requires explicit broker credentials unless the operator
        # deliberately opts in to anonymous access.
        if self.is_production and not self.MQTT_ALLOW_ANONYMOUS:
            if not self.MQTT_USERNAME.strip() or not self.MQTT_PASSWORD:
                fatal.append(
                    "MQTT_USERNAME and MQTT_PASSWORD are required in production "
                    "(anonymous brokers are refused; set MQTT_ALLOW_ANONYMOUS=true "
                    "only for an isolated development deployment)."
                )

        if fatal:
            raise RuntimeError(
                "Refusing to start with an insecure configuration: "
                + " | ".join(fatal)
            )


settings = Settings()
