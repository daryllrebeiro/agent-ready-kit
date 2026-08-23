"""Release-blocking test suite verifying multi-tenant isolation and security boundaries."""

import sqlite3
import pytest

from packages.core.auth.context import TenantContext, UserRole
from packages.core.auth.keys import generate_api_key, hash_api_key, verify_api_key
from packages.core.schemas import ComponentStatus, Score, ScoreComponent
from packages.core.storage.tenant_repository import MultiTenantRepository


@pytest.fixture
def repo():
    conn = sqlite3.connect(":memory:")
    return MultiTenantRepository(conn)


def test_api_key_generation_and_verification():
    raw_key, key_hash = generate_api_key()
    assert raw_key.startswith("ark_live_")
    assert len(key_hash) == 64
    assert verify_api_key(raw_key, key_hash) is True
    assert verify_api_key("wrong_key", key_hash) is False


def test_tenant_isolation_cross_organization_blocked(repo):
    # Setup Org A and Org B
    repo.create_organization("org_alpha", "Alpha Corp", tier="growth")
    repo.create_organization("org_beta", "Beta LLC", tier="growth")

    ctx_alpha = TenantContext(org_id="org_alpha", user_id="user_1", role=UserRole.ADMIN)
    ctx_beta = TenantContext(org_id="org_beta", user_id="user_2", role=UserRole.ADMIN)

    # Org A adds a domain
    domain_alpha = repo.add_domain(ctx_alpha, "https://alpha.example.com")
    assert domain_alpha["id"] is not None

    # Org B lists domains -> must NOT see Org A's domain
    beta_domains = repo.list_domains(ctx_beta)
    assert len(beta_domains) == 0

    # Org B tries to access Org A's domain by ID -> must return None
    assert repo.get_domain(ctx_beta, domain_alpha["id"]) is None

    # Org B tries to save a score on Org A's domain -> must raise PermissionError
    dummy_score = Score(
        url="https://alpha.example.com",
        version="score_v0.1",
        overall_score=80.0,
        grade="A",
        components=[],
        summary="Test",
        recommendations=[],
    )
    with pytest.raises(PermissionError):
        repo.save_score(ctx_beta, domain_alpha["id"], dummy_score)


def test_role_based_permissions(repo):
    repo.create_organization("org_gamma", "Gamma Inc")
    ctx_readonly = TenantContext(org_id="org_gamma", user_id="user_ro", role=UserRole.READ_ONLY)

    # Read-only user cannot add domains
    with pytest.raises(PermissionError):
        repo.add_domain(ctx_readonly, "https://gamma.com")
