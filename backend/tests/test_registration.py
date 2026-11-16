"""Registration gate: first account is owner, later sign-ups need an explicit opt-in."""

from app.api.routes.auth import registration_role
from app.config import Settings
from app.models.user import UserRole


def test_first_account_is_owner_even_when_closed():
    assert registration_role(0, allow_registration=False) is UserRole.owner


def test_later_accounts_rejected_by_default():
    assert registration_role(1, allow_registration=False) is None
    assert registration_role(5, allow_registration=False) is None


def test_later_accounts_allowed_when_opened():
    assert registration_role(1, allow_registration=True) is UserRole.operator


def test_registration_closed_by_default():
    assert Settings.model_fields["allow_registration"].default is False


def test_registration_flag_not_editable_at_runtime():
    from app.core.system_settings import SETTINGS_SCHEMA

    assert "allow_registration" not in SETTINGS_SCHEMA
