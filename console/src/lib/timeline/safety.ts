/** Safety invariant tri-state helpers for console timeline display. */

export type SafetyInvariantValue = boolean | null;

export interface TimelineSafetyInvariants {
  audit_chain_intact: SafetyInvariantValue;
  no_unauthorized_mutation: SafetyInvariantValue;
  no_policy_block_overridden: SafetyInvariantValue;
  no_grant_double_consume: SafetyInvariantValue;
  redaction_complete: SafetyInvariantValue;
}

export const SAFETY_INVARIANT_KEYS = [
  "audit_chain_intact",
  "no_unauthorized_mutation",
  "no_policy_block_overridden",
  "no_grant_double_consume",
  "redaction_complete",
] as const satisfies ReadonlyArray<keyof TimelineSafetyInvariants>;

export const UNKNOWN_SAFETY_INVARIANTS: TimelineSafetyInvariants = {
  audit_chain_intact: null,
  no_unauthorized_mutation: null,
  no_policy_block_overridden: null,
  no_grant_double_consume: null,
  redaction_complete: null,
};

export type SafetyInvariantApiPayload = Partial<Record<keyof TimelineSafetyInvariants, boolean>>;

export function safetyInvariantsFromApi(
  raw?: SafetyInvariantApiPayload | null,
): TimelineSafetyInvariants {
  if (!raw) {
    return { ...UNKNOWN_SAFETY_INVARIANTS };
  }
  const result = { ...UNKNOWN_SAFETY_INVARIANTS };
  for (const key of SAFETY_INVARIANT_KEYS) {
    if (Object.prototype.hasOwnProperty.call(raw, key)) {
      const value = raw[key];
      result[key] = typeof value === "boolean" ? value : null;
    }
  }
  return result;
}

export interface SafetyInvariantDisplay {
  symbol: string;
  detail: string;
  tone: "verified" | "failed" | "unknown";
}

export function formatSafetyInvariantDisplay(value: SafetyInvariantValue): SafetyInvariantDisplay {
  if (value === true) {
    return { symbol: "✓", detail: "verified", tone: "verified" };
  }
  if (value === false) {
    return { symbol: "✗", detail: "failed", tone: "failed" };
  }
  return { symbol: "—", detail: "not verified", tone: "unknown" };
}
