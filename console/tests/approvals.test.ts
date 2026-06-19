import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

import { decideApproval, newIdempotencyKey } from "@/lib/api/approvals";

const TEST_TOKEN =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." +
  "eyJzdWIiOiJ1c2VyOmRldiIsInRlbmFudF9pZCI6InRlbmFudC1hIiwicm9sZXMiOlsibWFpbnRhaW5lciJdLCJleHAiOjQwMDAwMDAwMDB9." +
  "test-signature";

describe("approval decide", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockResolvedValue({
      ok: true,
      headers: { get: () => "application/json" },
      json: async () => ({ approval_id: "approval-1", status: "approved" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "11111111-2222-4333-8444-555555555555" });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("generates idempotency keys", () => {
    expect(newIdempotencyKey()).toBe("11111111-2222-4333-8444-555555555555");
  });

  it("posts decide with Idempotency-Key header only for mutation", async () => {
    await decideApproval(
      {
        accessToken: TEST_TOKEN,
        expiresAtMs: Date.now() + 60_000,
        tenantId: "tenant-a",
        actorId: "user:dev",
        roles: ["maintainer"],
      },
      "approval-1",
      "approved",
      "reviewed in console",
    );
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = new Headers(init.headers);
    expect(headers.get("Idempotency-Key")).toBe("11111111-2222-4333-8444-555555555555");
    expect(headers.get("X-Tenant-Id")).toBe("tenant-a");
    expect(headers.get("Authorization")).toBe(`Bearer ${TEST_TOKEN}`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      decision: "approved",
      rationale: "reviewed in console",
    });
  });
});
