/** Console display redaction aligned with strict trace export (v2.3.2). */

export type DisplayRedactionProfile = "strict" | "standard" | "debug";

export const DEFAULT_DISPLAY_PROFILE: DisplayRedactionProfile = "strict";

const STRICT_HIDDEN_FIELDS = new Set([
  "debug",
  "debug_payload",
  "raw_prompt",
  "raw_model_prompt",
  "file_content",
  "secret",
  "secrets",
  "password",
  "api_key",
  "private_key",
  "token",
]);

const SECRET_PATTERNS: RegExp[] = [
  /ghp_[A-Za-z0-9]{20,}/g,
  /gho_[A-Za-z0-9]{20,}/g,
  /sk-[A-Za-z0-9]{10,}/g,
  /password=\S+/gi,
];

export const TIMELINE_SECTION_ORDER = [
  "Summary",
  "Timeline",
  "Citations",
  "Tool Calls",
  "Approvals",
  "Validation",
  "Cost and Token Summary",
  "Safety Invariants",
  "Failures",
] as const;

export function redactSecretsInText(value: string): string {
  let output = value;
  for (const pattern of SECRET_PATTERNS) {
    output = output.replace(pattern, "[REDACTED]");
  }
  return output;
}

export function isStrictHiddenField(fieldName: string): boolean {
  const normalized = fieldName.toLowerCase();
  if (STRICT_HIDDEN_FIELDS.has(normalized)) {
    return true;
  }
  return normalized.startsWith("tool_input");
}

export function redactFieldForDisplay(
  fieldName: string,
  value: string,
  profile: DisplayRedactionProfile = DEFAULT_DISPLAY_PROFILE,
): string {
  const redacted = redactSecretsInText(value);
  if (profile === "strict" && isStrictHiddenField(fieldName)) {
    return "[redacted]";
  }
  if (profile === "strict" && redacted.length > 2048) {
    return `${redacted.slice(0, 2048)}…[truncated]`;
  }
  return redacted;
}

export function redactObjectForDisplay(
  value: unknown,
  profile: DisplayRedactionProfile = DEFAULT_DISPLAY_PROFILE,
  fieldName = "value",
): unknown {
  if (typeof value === "string") {
    return redactFieldForDisplay(fieldName, value, profile);
  }
  if (Array.isArray(value)) {
    return value.map((item, index) => redactObjectForDisplay(item, profile, `${fieldName}[${index}]`));
  }
  if (value !== null && typeof value === "object") {
    const output: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      if (profile === "strict" && isStrictHiddenField(key)) {
        output[key] = "[redacted]";
        continue;
      }
      output[key] = redactObjectForDisplay(item, profile, key);
    }
    return output;
  }
  return value;
}

export function serializeForDisplay(
  value: unknown,
  profile: DisplayRedactionProfile = DEFAULT_DISPLAY_PROFILE,
): string {
  return JSON.stringify(redactObjectForDisplay(value, profile), null, 2);
}
