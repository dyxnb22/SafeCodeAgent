/** Tenant guard helpers (v2.3.1). */

import { tenantMatchesRoute } from "@/lib/auth/claims";
import type { ConsoleSession } from "@/lib/auth/session";

export type TenantAccessVerdict = "allowed" | "unauthenticated" | "tenant_mismatch";

export function evaluateTenantAccess(
  session: ConsoleSession | null,
  routeTenantId: string | null | undefined,
): TenantAccessVerdict {
  if (!session) {
    return "unauthenticated";
  }
  if (!tenantMatchesRoute(session.tenantId, routeTenantId)) {
    return "tenant_mismatch";
  }
  return "allowed";
}

export function tenantScopedPath(tenantId: string, segment: string): string {
  const normalized = tenantId.trim();
  const path = segment.startsWith("/") ? segment : `/${segment}`;
  return `/t/${encodeURIComponent(normalized)}${path}`;
}
