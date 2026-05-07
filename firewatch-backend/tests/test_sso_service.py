"""Unit tests for app.services.sso_service.provision_sso_user."""

from __future__ import annotations

import logging

import pytest

from app.core.config import settings
from app.models.user import User, UserRole
from app.services.sso_service import (
    SSOAccountDisabledError,
    SSOEmailNotVerifiedError,
    SSOMissingSubError,
    SSONoEmailError,
    provision_sso_user,
)


def _claims(**overrides):
    base = {
        "sub": "sub-123",
        "email": "newuser@example.com",
        "name": "New User",
        "email_verified": True,
    }
    base.update(overrides)
    return base


# --- JIT + lookup --------------------------------------------------------------


def test_jit_creates_new_user(db, oidc_settings):
    user = provision_sso_user(db, _claims())
    assert user.id is not None
    assert user.email == "newuser@example.com"
    assert user.full_name == "New User"
    assert user.auth_provider == "oidc"
    assert user.external_id == "sub-123"
    assert user.hashed_password is None
    assert user.is_active is True
    assert user.role == UserRole.risk_owner


def test_existing_user_by_external_id(db, oidc_settings):
    existing = User(
        email="existing@example.com",
        full_name="Existing",
        hashed_password=None,
        role=UserRole.risk_owner,
        auth_provider="oidc",
        external_id="sub-existing",
        is_active=True,
    )
    db.add(existing)
    db.commit()
    db.refresh(existing)

    result = provision_sso_user(
        db, _claims(sub="sub-existing", email="newaddr@example.com")
    )
    # Same row returned even though the email in the claim differs.
    assert result.id == existing.id
    assert result.email == "existing@example.com"


def test_existing_user_by_email_links_external_id(db, oidc_settings, existing_local_user):
    result = provision_sso_user(
        db, _claims(sub="sub-link-me", email=existing_local_user.email)
    )
    assert result.id == existing_local_user.id
    assert result.external_id == "sub-link-me"
    # Auth provider is *not* changed — local + sso coexist.
    assert result.auth_provider == "local"


def test_role_refreshed_on_existing_user(db, monkeypatch, oidc_settings):
    monkeypatch.setattr(
        settings, "OIDC_ROLE_MAP", {"firewatch-admins": UserRole.admin}
    )
    existing = User(
        email="bumpme@example.com",
        full_name="Bump",
        hashed_password=None,
        role=UserRole.risk_owner,
        auth_provider="oidc",
        external_id="sub-bump",
        is_active=True,
    )
    db.add(existing)
    db.commit()
    db.refresh(existing)

    result = provision_sso_user(
        db,
        _claims(sub="sub-bump", email="bumpme@example.com", groups=["firewatch-admins"]),
    )
    assert result.id == existing.id
    assert result.role == UserRole.admin


def test_disabled_sso_user_raises(db, oidc_settings, disabled_sso_user):
    with pytest.raises(SSOAccountDisabledError):
        provision_sso_user(
            db, _claims(sub="disabled-sub", email="disabled@example.com")
        )


def test_disabled_user_matched_by_email_raises(db, oidc_settings):
    user = User(
        email="off@example.com",
        full_name="Off",
        hashed_password=None,
        role=UserRole.risk_owner,
        auth_provider="local",
        external_id=None,
        is_active=False,
    )
    db.add(user)
    db.commit()
    with pytest.raises(SSOAccountDisabledError):
        provision_sso_user(db, _claims(sub="brand-new-sub", email="off@example.com"))


# --- Required claim validation -------------------------------------------------


def test_missing_sub_raises(db, oidc_settings):
    with pytest.raises(SSOMissingSubError):
        provision_sso_user(db, _claims(sub=None))


def test_missing_email_raises(db, oidc_settings):
    with pytest.raises(SSONoEmailError):
        provision_sso_user(db, _claims(email=None))


def test_email_verified_false_raises(db, oidc_settings):
    """Gap 1 regression — explicit email_verified=False must reject."""
    with pytest.raises(SSOEmailNotVerifiedError):
        provision_sso_user(db, _claims(email_verified=False))


def test_email_verified_absent_is_accepted(db, oidc_settings):
    claims = _claims()
    claims.pop("email_verified")
    user = provision_sso_user(db, claims)
    assert user.id is not None


def test_email_verified_true_is_accepted(db, oidc_settings):
    user = provision_sso_user(db, _claims(email_verified=True))
    assert user.id is not None


# --- Role mapping --------------------------------------------------------------


def test_role_map_with_single_value(db, monkeypatch, oidc_settings):
    monkeypatch.setattr(
        settings,
        "OIDC_ROLE_MAP",
        {"analysts": UserRole.security_analyst},
    )
    user = provision_sso_user(db, _claims(groups="analysts"))
    assert user.role == UserRole.security_analyst


def test_role_map_with_list_takes_highest_privilege(db, monkeypatch, oidc_settings):
    monkeypatch.setattr(
        settings,
        "OIDC_ROLE_MAP",
        {
            "viewers": UserRole.executive_viewer,
            "owners": UserRole.risk_owner,
            "admins": UserRole.admin,
        },
    )
    user = provision_sso_user(
        db, _claims(groups=["viewers", "admins", "owners"])
    )
    assert user.role == UserRole.admin


def test_role_map_no_match_returns_default(db, monkeypatch, oidc_settings):
    monkeypatch.setattr(
        settings, "OIDC_ROLE_MAP", {"admins": UserRole.admin}
    )
    user = provision_sso_user(db, _claims(groups=["nothing-matches"]))
    assert user.role == UserRole.risk_owner  # OIDC_DEFAULT_ROLE


def test_group_overage_logs_warning(db, oidc_settings, caplog):
    overage_claims = _claims(_claim_names={"groups": "src1"})
    overage_claims.pop("groups", None)
    with caplog.at_level(logging.WARNING, logger="app.services.sso_service"):
        provision_sso_user(db, overage_claims)
    assert any("group overage" in r.message for r in caplog.records)
