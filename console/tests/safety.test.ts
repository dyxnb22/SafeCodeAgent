import { describe, expect, it } from "vitest";

import {
  UNKNOWN_SAFETY_INVARIANTS,
  formatSafetyInvariantDisplay,
  safetyInvariantsFromApi,
} from "@/lib/timeline/safety";
import { timelineFromApi } from "@/lib/api/runs";

describe("safetyInvariantsFromApi", () => {
  it("returns unknown values when API omits safety invariants", () => {
    expect(safetyInvariantsFromApi(undefined)).toEqual(UNKNOWN_SAFETY_INVARIANTS);
    expect(safetyInvariantsFromApi(null)).toEqual(UNKNOWN_SAFETY_INVARIANTS);
    expect(safetyInvariantsFromApi({})).toEqual(UNKNOWN_SAFETY_INVARIANTS);
  });

  it("preserves explicit true and false values from API", () => {
    expect(
      safetyInvariantsFromApi({
        audit_chain_intact: true,
        redaction_complete: false,
      }),
    ).toEqual({
      audit_chain_intact: true,
      no_unauthorized_mutation: null,
      no_policy_block_overridden: null,
      no_grant_double_consume: null,
      redaction_complete: false,
    });
  });
});

describe("formatSafetyInvariantDisplay", () => {
  it("renders verified, failed, and unknown states", () => {
    expect(formatSafetyInvariantDisplay(true)).toEqual({
      symbol: "✓",
      detail: "verified",
      tone: "verified",
    });
    expect(formatSafetyInvariantDisplay(false)).toEqual({
      symbol: "✗",
      detail: "failed",
      tone: "failed",
    });
    expect(formatSafetyInvariantDisplay(null)).toEqual({
      symbol: "—",
      detail: "not verified",
      tone: "unknown",
    });
  });
});

describe("timelineFromApi safety invariants", () => {
  const runSummary = {
    run_id: "run-1",
    tenant_id: "tenant-a",
    task_type: "pr_review",
    status: "completed",
    created_at: "2026-06-19T00:00:00Z",
    updated_at: "2026-06-19T00:01:00Z",
  };

  it("does not default missing safety invariants to true", () => {
    const timeline = timelineFromApi(runSummary, {
      run_id: "run-1",
      events: [],
    });
    expect(timeline.safety_invariants).toEqual(UNKNOWN_SAFETY_INVARIANTS);
    expect(Object.values(timeline.safety_invariants).every((value) => value !== true)).toBe(true);
  });

  it("maps explicit API safety values without inventing others", () => {
    const timeline = timelineFromApi(runSummary, {
      run_id: "run-1",
      events: [],
      safety_invariants: {
        redaction_complete: true,
        audit_chain_intact: false,
      },
    });
    expect(timeline.safety_invariants.redaction_complete).toBe(true);
    expect(timeline.safety_invariants.audit_chain_intact).toBe(false);
    expect(timeline.safety_invariants.no_unauthorized_mutation).toBeNull();
  });
});
