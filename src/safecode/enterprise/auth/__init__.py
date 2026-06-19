"""Enterprise authentication helpers (v2.1.6)."""

from safecode.enterprise.auth.oidc import (
    DEFAULT_ALLOWED_ALGORITHMS,
    DEFAULT_CLOCK_SKEW_SECONDS,
    JwksKeyCache,
    OidcDiscoveryConfig,
    OidcValidator,
    StaticJwksProvider,
    TokenClaims,
    TokenValidationError,
    build_oidc_validator,
    load_oidc_discovery,
)
from safecode.enterprise.auth.subject import (
    ROLE_CLAIM,
    SINGLE_ROLE_CLAIM,
    TENANT_CLAIM,
    SubjectMappingError,
    map_claims_to_subject,
)

__all__ = [
    "DEFAULT_ALLOWED_ALGORITHMS",
    "DEFAULT_CLOCK_SKEW_SECONDS",
    "JwksKeyCache",
    "OidcDiscoveryConfig",
    "OidcValidator",
    "ROLE_CLAIM",
    "SINGLE_ROLE_CLAIM",
    "StaticJwksProvider",
    "TENANT_CLAIM",
    "SubjectMappingError",
    "TokenClaims",
    "TokenValidationError",
    "build_oidc_validator",
    "load_oidc_discovery",
    "map_claims_to_subject",
]
