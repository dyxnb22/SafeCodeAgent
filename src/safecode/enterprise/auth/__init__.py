"""Enterprise authentication helpers (v2.1.6).

中文说明
--------
企业认证辅助：OIDC 发现/JWKS 缓存、JWT 签名校验（``OidcValidator``），
以及将令牌声明映射为 ``RBACSubject``（租户、角色）。API 层在 SERVER 模式下
启用 OIDC；本地模式使用可配置的静态主体解析器。

安全要点：认证仅确立身份与租户边界，不授予写操作执行权；
模型输出与令牌自定义声明均不可信，执行仍须经策略门控与人工审批。
"""

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
