/** JWT claim helpers for tenant-aware routing (v2.3.1). */

export interface TokenClaims {
  sub: string;
  tenant_id: string;
  roles: string[];
  exp: number;
}

const FORBIDDEN_IN_URL = ["eyJ", "ghp_", "gho_", "sk-"];

export function tokenAppearsInUrl(value: string): boolean {
  return FORBIDDEN_IN_URL.some((token) => value.includes(token));
}

function base64UrlDecode(input: string): string {
  if (typeof Buffer !== "undefined") {
    return Buffer.from(input, "base64url").toString("utf-8");
  }
  const padded = input.replace(/-/g, "+").replace(/_/g, "/");
  return atob(padded);
}

export function decodeJwtPayload(token: string): TokenClaims {
  const parts = token.split(".");
  if (parts.length !== 3) {
    throw new Error("invalid bearer token format");
  }
  const payloadJson = base64UrlDecode(parts[1]);
  const payload = JSON.parse(payloadJson) as Record<string, unknown>;
  const sub = String(payload.sub || "");
  const tenantId = String(payload.tenant_id || payload.tenant || "");
  if (!sub || !tenantId) {
    throw new Error("token missing subject or tenant_id claim");
  }
  const rolesRaw = payload.roles ?? payload.role;
  const roles = Array.isArray(rolesRaw)
    ? rolesRaw.map(String)
    : rolesRaw
      ? [String(rolesRaw)]
      : [];
  const exp = Number(payload.exp || 0);
  if (!exp) {
    throw new Error("token missing exp claim");
  }
  return { sub, tenant_id: tenantId, roles, exp };
}

export function claimsExpired(claims: TokenClaims, nowMs: number = Date.now()): boolean {
  return claims.exp * 1000 <= nowMs;
}

export function tenantMatchesRoute(sessionTenant: string, routeTenant: string | null | undefined): boolean {
  if (!routeTenant) {
    return true;
  }
  return sessionTenant.trim() === routeTenant.trim();
}
