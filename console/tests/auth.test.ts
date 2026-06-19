import { describe, expect, it } from "vitest";

import { claimsExpired, decodeJwtPayload, tenantMatchesRoute, tokenAppearsInUrl } from "@/lib/auth/claims";
import { validateOidcCallbackQuery } from "@/lib/auth/oidc";
import {
  SESSION_STORAGE_KEY,
  createSessionStore,
  isAuthenticated,
  sessionFromAccessToken,
} from "@/lib/auth/session";
import { evaluateTenantAccess } from "@/lib/tenant/guards";

const TEST_TOKEN =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." +
  "eyJzdWIiOiJ1c2VyOmRldiIsInRlbmFudF9pZCI6InRlbmFudC1hIiwicm9sZXMiOlsibWFpbnRhaW5lciJdLCJleHAiOjQwMDAwMDAwMDB9." +
  "test-signature";

describe("session storage", () => {
  it("stores bearer session in sessionStorage only", () => {
    const memory = new Map<string, string>();
    const store = createSessionStore({
      getItem: (key) => memory.get(key) ?? null,
      setItem: (key, value) => {
        memory.set(key, value);
      },
      removeItem: (key) => {
        memory.delete(key);
      },
    });
    const session = sessionFromAccessToken(TEST_TOKEN);
    store.set(session);
    expect(memory.has(SESSION_STORAGE_KEY)).toBe(true);
    expect(isAuthenticated(store.get())).toBe(true);
  });

  it("clears expired sessions", () => {
    const memory = new Map<string, string>();
    const store = createSessionStore({
      getItem: (key) => memory.get(key) ?? null,
      setItem: (key, value) => memory.set(key, value),
      removeItem: (key) => memory.delete(key),
    });
    store.set({
      accessToken: TEST_TOKEN,
      expiresAtMs: Date.now() - 1,
      tenantId: "tenant-a",
      actorId: "user:dev",
      roles: ["maintainer"],
    });
    expect(store.get()).toBeNull();
  });
});

describe("tenant guards", () => {
  it("allows matching tenant routes", () => {
    const session = sessionFromAccessToken(TEST_TOKEN);
    expect(evaluateTenantAccess(session, "tenant-a")).toBe("allowed");
  });

  it("rejects cross-tenant routes", () => {
    const session = sessionFromAccessToken(TEST_TOKEN);
    expect(evaluateTenantAccess(session, "tenant-b")).toBe("tenant_mismatch");
  });

  it("requires authentication", () => {
    expect(evaluateTenantAccess(null, "tenant-a")).toBe("unauthenticated");
  });
});

describe("oidc callback", () => {
  it("rejects implicit tokens in callback URL", () => {
    const params = new URLSearchParams("access_token=eyJ.test.test&state=abc");
    expect(() => validateOidcCallbackQuery(params)).toThrow(/implicit tokens/);
  });

  it("accepts authorization code callback", () => {
    const params = new URLSearchParams("code=abc123&state=xyz");
    expect(validateOidcCallbackQuery(params)).toEqual({ code: "abc123", state: "xyz" });
  });
});

describe("claims", () => {
  it("decodes tenant and subject claims", () => {
    const claims = decodeJwtPayload(TEST_TOKEN);
    expect(claims.sub).toBe("user:dev");
    expect(claims.tenant_id).toBe("tenant-a");
    expect(claims.roles).toContain("maintainer");
  });

  it("detects tokens in URLs", () => {
    expect(tokenAppearsInUrl("https://app.example?token=eyJhbGciOi")).toBe(true);
    expect(tokenAppearsInUrl("https://app.example/login")).toBe(false);
  });

  it("matches route tenant ids", () => {
    expect(tenantMatchesRoute("tenant-a", "tenant-a")).toBe(true);
    expect(tenantMatchesRoute("tenant-a", "tenant-b")).toBe(false);
  });

  it("flags expired claims", () => {
    const claims = decodeJwtPayload(TEST_TOKEN);
    expect(claimsExpired(claims, 5_000_000_000_000)).toBe(true);
  });
});
