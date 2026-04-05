"""Startup security checks — called once during lifespan."""

import logging

from app.config import settings

logger = logging.getLogger(__name__)

_INSECURE_SECRET_KEYS = {"change-me-in-production", "secret", "dev", "test", ""}
_MIN_SECRET_KEY_LENGTH = 32


class StartupSecurityError(RuntimeError):
    """Raised when a fatal security misconfiguration is detected in strict mode."""


def run_startup_checks(strict: bool = False) -> None:
    """Validate security-critical settings on application startup.

    In strict mode (production), any failure raises StartupSecurityError.
    In non-strict mode (dev), issues are logged as warnings.
    """
    issues: list[str] = []

    # 1. SECRET_KEY strength
    if settings.secret_key in _INSECURE_SECRET_KEYS:
        issues.append("SECRET_KEY is set to an insecure default value")
    elif len(settings.secret_key) < _MIN_SECRET_KEY_LENGTH:
        issues.append(f"SECRET_KEY is too short (minimum {_MIN_SECRET_KEY_LENGTH} characters)")

    # 2. ENCRYPTION_KEY validity
    if settings.encryption_key:
        try:
            from cryptography.fernet import Fernet
            Fernet(settings.encryption_key.encode())
        except Exception:
            issues.append("ENCRYPTION_KEY is present but is not a valid Fernet key")
    else:
        issues.append(
            "ENCRYPTION_KEY is not set — encrypted secrets will be lost on restart. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )

    # 3. Debug mode warning
    if settings.debug:
        issues.append("debug=True is set — disable in production (set DEBUG=false)")

    # 4. JWT refresh lifetime sanity check
    if settings.jwt_refresh_token_expire_days > 90:
        issues.append(
            f"JWT refresh token lifetime is very long "
            f"({settings.jwt_refresh_token_expire_days} days > 90)"
        )

    if not issues:
        logger.info("Security startup checks passed.")
        return

    for issue in issues:
        if strict:
            logger.error("SECURITY VIOLATION: %s", issue)
        else:
            logger.warning("SECURITY WARNING: %s", issue)

    if strict:
        raise StartupSecurityError(f"{len(issues)} security check(s) failed — refusing to start")
