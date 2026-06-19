/** Session storage for console bearer sessions (v2.3.1, D26). */

import { type TokenClaims, claimsExpired, decodeJwtPayload } from "@/lib/auth/claims";

export const SESSION_STORAGE_KEY = "safecode-console-session";

export interface ConsoleSession {
  accessToken: string;
  expiresAtMs: number;
  tenantId: string;
  actorId: string;
  roles: string[];
}

export interface SessionStore {
  get(): ConsoleSession | null;
  set(session: ConsoleSession): void;
  clear(): void;
}

export function createSessionStore(storage: Pick<Storage, "getItem" | "setItem" | "removeItem">): SessionStore {
  return {
    get() {
      const raw = storage.getItem(SESSION_STORAGE_KEY);
      if (!raw) {
        return null;
      }
      try {
        const parsed = JSON.parse(raw) as ConsoleSession;
        if (!parsed.accessToken || !parsed.tenantId || !parsed.expiresAtMs) {
          return null;
        }
        if (parsed.expiresAtMs <= Date.now()) {
          storage.removeItem(SESSION_STORAGE_KEY);
          return null;
        }
        return parsed;
      } catch {
        storage.removeItem(SESSION_STORAGE_KEY);
        return null;
      }
    },
    set(session: ConsoleSession) {
      storage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
    },
    clear() {
      storage.removeItem(SESSION_STORAGE_KEY);
    },
  };
}

export function sessionFromAccessToken(accessToken: string, nowMs: number = Date.now()): ConsoleSession {
  const claims = decodeJwtPayload(accessToken);
  if (claimsExpired(claims, nowMs)) {
    throw new Error("token expired");
  }
  return {
    accessToken,
    expiresAtMs: claims.exp * 1000,
    tenantId: claims.tenant_id,
    actorId: claims.sub,
    roles: claims.roles,
  };
}

export function isAuthenticated(session: ConsoleSession | null): boolean {
  return session !== null && session.expiresAtMs > Date.now();
}

export type { TokenClaims };
