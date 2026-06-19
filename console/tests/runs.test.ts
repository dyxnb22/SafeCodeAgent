import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

import { timelineSectionNames } from "@/components/timeline/RunTimelineView";
import { TIMELINE_SECTION_ORDER } from "@/lib/redaction/display";
import { apiFetchPath } from "@/lib/api/client";
import { timelineFromApi } from "@/lib/api/runs";
import {
  isStrictHiddenField,
  redactFieldForDisplay,
  redactObjectForDisplay,
  serializeForDisplay,
} from "@/lib/redaction/display";

const TEST_TOKEN =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." +
  "eyJzdWIiOiJ1c2VyOmRldiIsInRlbmFudF9pZCI6InRlbmFudC1hIiwicm9sZXMiOlsibWFpbnRhaW5lciJdLCJleHAiOjQwMDAwMDAwMDB9." +
  "test-signature";

describe("timeline sections", () => {
  it("matches python render_markdown section order", () => {
    expect(timelineSectionNames()).toEqual([...TIMELINE_SECTION_ORDER]);
  });
});

describe("strict display redaction", () => {
  it("hides raw_prompt and debug fields", () => {
    expect(isStrictHiddenField("raw_prompt")).toBe(true);
    expect(isStrictHiddenField("debug_payload")).toBe(true);
    expect(isStrictHiddenField("secrets")).toBe(true);
    expect(redactFieldForDisplay("raw_prompt", "secret prompt")).toBe("[redacted]");
  });

  it("redacts secrets in nested objects", () => {
    const payload = {
      summary: "ok",
      raw_prompt: "secret",
      debug_payload: "internal",
      nested: { token: "ghp_abcdefghijklmnopqrstuvwxyz1234567890abcd" },
    };
    const redacted = redactObjectForDisplay(payload) as Record<string, unknown>;
    expect(redacted.raw_prompt).toBe("[redacted]");
    expect(redacted.debug_payload).toBe("[redacted]");
    expect(serializeForDisplay(payload)).not.toContain("ghp_");
  });
});

describe("api client headers", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockResolvedValue({
      ok: true,
      headers: { get: () => "application/json" },
      json: async () => ({ items: [] }),
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends Authorization and tenant_id on reads", async () => {
    await apiFetchPath("/v2/runs", {
      tenantId: "tenant-a",
      accessToken: TEST_TOKEN,
    });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = new Headers(init.headers);
    expect(headers.get("Authorization")).toBe(`Bearer ${TEST_TOKEN}`);
    expect(fetchMock.mock.calls[0][0]).toContain("tenant_id=tenant-a");
  });

  it("sends X-Tenant-Id and Idempotency-Key on writes", async () => {
    await apiFetchPath("/v2/approvals/a1/decide", {
      method: "POST",
      tenantId: "tenant-a",
      accessToken: TEST_TOKEN,
      tenantHeader: true,
      idempotencyKey: "console-key-001",
      body: { decision: "approved", rationale: "ok" },
    });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = new Headers(init.headers);
    expect(headers.get("X-Tenant-Id")).toBe("tenant-a");
    expect(headers.get("Idempotency-Key")).toBe("console-key-001");
  });
});

describe("timelineFromApi", () => {
  it("maps timeline events into node rows", () => {
    const timeline = timelineFromApi(
      {
        run_id: "run-1",
        tenant_id: "tenant-a",
        task_type: "pr_review",
        status: "completed",
        created_at: "2026-06-19T00:00:00Z",
        updated_at: "2026-06-19T00:01:00Z",
      },
      {
        run_id: "run-1",
        events: [{ event_type: "node.analyze", timestamp: "2026-06-19T00:00:30Z", summary: "done" }],
      },
    );
    expect(timeline.nodes).toHaveLength(1);
    expect(timeline.nodes[0].name).toBe("node.analyze");
  });
});
