"""Integration tests for /api/scim/v2 (SCIM 2.0 provisioning)."""

from __future__ import annotations

import json

import pytest

from app.core.config import settings
from app.models.audit_log import AuditLog
from app.models.user import User, UserRole


SCIM_BASE = "/api/scim/v2"
AUTH_HEADERS = {"Authorization": "Bearer test-token"}


@pytest.fixture
def scim_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Turn SCIM on with a known shared-secret bearer token for tests."""
    monkeypatch.setattr(settings, "SCIM_ENABLED", True)
    monkeypatch.setattr(settings, "SCIM_BEARER_TOKEN", "test-token")
    monkeypatch.setattr(settings, "OIDC_DEFAULT_ROLE", "risk_owner")


# --- Auth gating ---------------------------------------------------------------


def test_scim_disabled_returns_503(client):
    # SCIM_ENABLED defaults to False
    resp = client.get(f"{SCIM_BASE}/ServiceProviderConfig", headers=AUTH_HEADERS)
    assert resp.status_code == 503


def test_scim_missing_bearer_returns_401(client, scim_enabled):
    resp = client.get(f"{SCIM_BASE}/ServiceProviderConfig")
    assert resp.status_code == 401


def test_scim_wrong_bearer_returns_401(client, scim_enabled):
    resp = client.get(
        f"{SCIM_BASE}/ServiceProviderConfig",
        headers={"Authorization": "Bearer wrong"},
    )
    assert resp.status_code == 401


def test_scim_wrong_scheme_returns_401(client, scim_enabled):
    resp = client.get(
        f"{SCIM_BASE}/ServiceProviderConfig",
        headers={"Authorization": "Basic test-token"},
    )
    assert resp.status_code == 401


# --- ServiceProviderConfig -----------------------------------------------------


def test_service_provider_config_returns_static_payload(client, scim_enabled):
    resp = client.get(f"{SCIM_BASE}/ServiceProviderConfig", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["patch"]["supported"] is True
    assert body["bulk"]["supported"] is False
    assert body["filter"]["supported"] is True
    assert body["filter"]["maxResults"] == 200
    assert body["authenticationSchemes"][0]["type"] == "oauthbearertoken"


def test_resource_types_returns_user_entry(client, scim_enabled):
    resp = client.get(f"{SCIM_BASE}/ResourceTypes", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert any(r["id"] == "User" for r in body)


def test_schemas_returns_user_schema(client, scim_enabled):
    resp = client.get(f"{SCIM_BASE}/Schemas", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert any(
        s["id"] == "urn:ietf:params:scim:schemas:core:2.0:User" for s in body
    )


# --- POST /Users ---------------------------------------------------------------


def test_create_user_succeeds_with_defaults(client, scim_enabled, db):
    payload = {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "userName": "new.scim@example.com",
        "externalId": "ext-1",
        "name": {"givenName": "New", "familyName": "Scim"},
        "emails": [{"value": "new.scim@example.com", "primary": True, "type": "work"}],
        "active": True,
    }
    resp = client.post(f"{SCIM_BASE}/Users", json=payload, headers=AUTH_HEADERS)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["userName"] == "new.scim@example.com"
    assert body["active"] is True
    assert body["meta"]["resourceType"] == "User"
    assert body["meta"]["location"].endswith(f"/api/scim/v2/Users/{body['id']}")

    user = db.query(User).filter(User.email == "new.scim@example.com").first()
    assert user is not None
    assert user.auth_provider == "oidc"
    assert user.role == UserRole.risk_owner
    assert user.is_active is True
    assert user.hashed_password is None
    assert user.external_id == "ext-1"
    assert user.full_name == "New Scim"


def test_create_user_duplicate_returns_409_uniqueness(client, scim_enabled, existing_local_user):
    payload = {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "userName": existing_local_user.email,
        "active": True,
    }
    resp = client.post(f"{SCIM_BASE}/Users", json=payload, headers=AUTH_HEADERS)
    assert resp.status_code == 409
    body = resp.json()
    assert body["scimType"] == "uniqueness"
    assert body["status"] == "409"


def test_create_user_audit_row_written(client, scim_enabled, db):
    payload = {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "userName": "audited@example.com",
        "active": True,
    }
    resp = client.post(f"{SCIM_BASE}/Users", json=payload, headers=AUTH_HEADERS)
    assert resp.status_code == 201
    row = db.query(AuditLog).filter(AuditLog.action == "scim.user.created").first()
    assert row is not None
    assert row.resource_type == "user"


# --- GET /Users (list + filter) ------------------------------------------------


def test_list_users_with_username_filter(client, scim_enabled, existing_local_user):
    resp = client.get(
        f'{SCIM_BASE}/Users?filter=userName eq "local@example.com"',
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalResults"] == 1
    assert body["Resources"][0]["userName"] == "local@example.com"


def test_list_users_with_externalid_filter(client, scim_enabled, db):
    user = User(
        email="ext@example.com",
        full_name="Ext User",
        hashed_password=None,
        role=UserRole.risk_owner,
        auth_provider="oidc",
        external_id="ext-id-xyz",
        is_active=True,
    )
    db.add(user)
    db.commit()
    resp = client.get(
        f'{SCIM_BASE}/Users?filter=externalId eq "ext-id-xyz"',
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalResults"] == 1
    assert body["Resources"][0]["externalId"] == "ext-id-xyz"


def test_list_users_invalid_filter_returns_400(client, scim_enabled):
    resp = client.get(
        f'{SCIM_BASE}/Users?filter=displayName co "bob"',
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 400
    assert resp.json()["scimType"] == "invalidFilter"


def test_list_users_filter_no_match_returns_empty(client, scim_enabled):
    resp = client.get(
        f'{SCIM_BASE}/Users?filter=userName eq "nobody@example.com"',
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalResults"] == 0
    assert body["Resources"] == []


# --- GET /Users/{id} -----------------------------------------------------------


def test_get_user_returns_scim_user(client, scim_enabled, existing_local_user):
    resp = client.get(
        f"{SCIM_BASE}/Users/{existing_local_user.id}", headers=AUTH_HEADERS
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["userName"] == existing_local_user.email
    assert body["id"] == str(existing_local_user.id)


def test_get_user_missing_returns_404(client, scim_enabled):
    resp = client.get(f"{SCIM_BASE}/Users/9999", headers=AUTH_HEADERS)
    assert resp.status_code == 404
    assert resp.json()["status"] == "404"


# --- PATCH /Users/{id} ---------------------------------------------------------


def test_patch_deactivates_user_and_stamps_logout(client, scim_enabled, existing_local_user, db):
    assert existing_local_user.last_logout_at is None
    payload = {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
        "Operations": [{"op": "replace", "path": "active", "value": False}],
    }
    resp = client.patch(
        f"{SCIM_BASE}/Users/{existing_local_user.id}",
        json=payload,
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["active"] is False

    db.refresh(existing_local_user)
    assert existing_local_user.is_active is False
    assert existing_local_user.last_logout_at is not None


def test_patch_deactivation_invalidates_existing_token(
    client, scim_enabled, existing_local_user, login_as, db
):
    # 1) Log in to obtain auth cookies for the user.
    login_as(existing_local_user)
    # Sanity check: /auth/me is authorized.
    me = client.get("/api/auth/me")
    assert me.status_code == 200

    # 2) SCIM PATCH deactivates the user.
    payload = {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
        "Operations": [{"op": "replace", "path": "active", "value": False}],
    }
    resp = client.patch(
        f"{SCIM_BASE}/Users/{existing_local_user.id}",
        json=payload,
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200

    # 3) The previously-valid cookie must now be rejected.
    me_after = client.get("/api/auth/me")
    assert me_after.status_code == 401


def test_patch_replace_username(client, scim_enabled, existing_local_user, db):
    payload = {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
        "Operations": [
            {"op": "replace", "path": "userName", "value": "renamed@example.com"}
        ],
    }
    resp = client.patch(
        f"{SCIM_BASE}/Users/{existing_local_user.id}",
        json=payload,
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    db.refresh(existing_local_user)
    assert existing_local_user.email == "renamed@example.com"


def test_patch_remove_active_treated_as_false(client, scim_enabled, existing_local_user, db):
    payload = {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
        "Operations": [{"op": "remove", "path": "active"}],
    }
    resp = client.patch(
        f"{SCIM_BASE}/Users/{existing_local_user.id}",
        json=payload,
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    db.refresh(existing_local_user)
    assert existing_local_user.is_active is False
    assert existing_local_user.last_logout_at is not None


def test_patch_audit_row_written(client, scim_enabled, existing_local_user, db):
    payload = {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
        "Operations": [{"op": "replace", "path": "active", "value": False}],
    }
    resp = client.patch(
        f"{SCIM_BASE}/Users/{existing_local_user.id}",
        json=payload,
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200

    row = db.query(AuditLog).filter(AuditLog.action == "scim.user.patched").first()
    assert row is not None
    assert row.resource_id == str(existing_local_user.id)
    assert row.details is not None
    decoded = json.loads(row.details)
    assert decoded["active"] is False


# --- PUT /Users/{id} -----------------------------------------------------------


def test_put_replaces_user(client, scim_enabled, existing_local_user, db):
    payload = {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "userName": "replaced@example.com",
        "externalId": "new-ext",
        "name": {"givenName": "Replaced", "familyName": "User"},
        "emails": [{"value": "replaced@example.com", "primary": True, "type": "work"}],
        "active": True,
    }
    resp = client.put(
        f"{SCIM_BASE}/Users/{existing_local_user.id}",
        json=payload,
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["userName"] == "replaced@example.com"
    db.refresh(existing_local_user)
    assert existing_local_user.email == "replaced@example.com"
    assert existing_local_user.external_id == "new-ext"
    assert existing_local_user.full_name == "Replaced User"


# --- DELETE /Users/{id} --------------------------------------------------------


def test_delete_deactivates_and_stamps_logout(
    client, scim_enabled, existing_local_user, db
):
    assert existing_local_user.is_active is True
    resp = client.delete(
        f"{SCIM_BASE}/Users/{existing_local_user.id}", headers=AUTH_HEADERS
    )
    assert resp.status_code == 204
    db.refresh(existing_local_user)
    assert existing_local_user.is_active is False
    assert existing_local_user.last_logout_at is not None

    row = db.query(AuditLog).filter(AuditLog.action == "scim.user.deleted").first()
    assert row is not None


def test_delete_missing_returns_404(client, scim_enabled):
    resp = client.delete(f"{SCIM_BASE}/Users/9999", headers=AUTH_HEADERS)
    assert resp.status_code == 404
