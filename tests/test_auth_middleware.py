"""Unit tests for Unified Auth Middleware & RBAC."""

from packages.core.auth.middleware import AuthManager, UserRole


def test_auth_manager_api_key_lifecycle():
    auth = AuthManager()

    # 1. Generate key
    raw_key = auth.generate_api_key(tenant_id="tenant_acme", role=UserRole.ADMIN)
    assert raw_key.startswith("ak_live_")

    # 2. Authenticate header with valid Bearer token
    ctx = auth.authenticate_header(f"Bearer {raw_key}")
    assert ctx is not None
    assert ctx.tenant_id == "tenant_acme"
    assert ctx.role == UserRole.ADMIN
    assert ctx.has_permission(UserRole.MEMBER) is True
    assert ctx.has_permission(UserRole.ADMIN) is True

    # 3. Test invalid Bearer token
    invalid_ctx = auth.authenticate_header("Bearer ak_live_invalid_key_123")
    assert invalid_ctx is None

    # 4. Test missing or malformed header
    assert auth.authenticate_header(None) is None
    assert auth.authenticate_header("Basic 12345") is None

    # 5. Revoke key
    revoked = auth.revoke_api_key(raw_key)
    assert revoked is True
    assert auth.authenticate_header(f"Bearer {raw_key}") is None


def test_auth_rbac_permissions():
    auth = AuthManager()

    raw_read_only = auth.generate_api_key(tenant_id="tenant_viewer", role=UserRole.READ_ONLY)
    ctx = auth.authenticate_header(f"Bearer {raw_read_only}")
    assert ctx is not None
    assert ctx.has_permission(UserRole.READ_ONLY) is True
    assert ctx.has_permission(UserRole.MEMBER) is False
    assert ctx.has_permission(UserRole.ADMIN) is False
