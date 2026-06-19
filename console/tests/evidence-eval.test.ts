import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

import { downloadEvidence } from "@/lib/api/evidence";
import { listEvalBaselines } from "@/lib/api/eval";

const TEST_TOKEN =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." +
  "eyJzdWIiOiJ1c2VyOmRldiIsInRlbmFudF9pZCI6InRlbmFudC1hIiwicm9sZXMiOlsibWFpbnRhaW5lciJdLCJleHAiOjQwMDAwMDAwMDB9." +
  "test-signature";

const session = {
  accessToken: TEST_TOKEN,
  expiresAtMs: Date.now() + 60_000,
  tenantId: "tenant-a",
  actorId: "user:dev",
  roles: ["maintainer"],
};

describe("evidence and eval reads", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockResolvedValue({
      ok: true,
      headers: { get: () => "application/json" },
      json: async () => ({ items: [{ suite: "retrieval", baseline_id: "retrieval_v1" }] }),
      blob: async () => new Blob(["PK"], { type: "application/zip" }),
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("lists eval baselines read-only", async () => {
    const payload = await listEvalBaselines(session);
    expect(payload.items[0].suite).toBe("retrieval");
    expect(fetchMock.mock.calls[0][0]).toContain("/v2/eval/baselines");
  });

  it("downloads evidence as zip", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      headers: { get: () => "application/zip" },
      blob: async () => new Blob(["PK"], { type: "application/zip" }),
    });
    const blob = await downloadEvidence(session, "run-1");
    expect(blob.type).toBe("application/zip");
    expect(fetchMock.mock.calls[0][0]).toContain("/v2/evidence/run-1");
  });
});
