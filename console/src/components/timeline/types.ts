/** RunTimeline types aligned with Enterprise v1.5 schema (v2.3.2). */

import type { SafetyInvariantApiPayload, TimelineSafetyInvariants } from "@/lib/timeline/safety";

export interface TimelineNode {
  name: string;
  status: string;
  started_at: string;
  ended_at: string;
  duration_ms: number;
  summary: string;
  events: string[];
  artifacts: Array<{ name: string; kind: string; ref: string }>;
}

export interface TimelineCitation {
  citation_id: string;
  source_id: string;
  source_type: string;
  path: string;
  start_line: number;
  end_line: number;
  score: number;
  selection_reason: string;
  permission_verdict: string;
  freshness: string;
  hash: string;
  text_excerpt: string;
  redacted: boolean;
}

export interface TimelineToolCall {
  call_id: string;
  tool_name: string;
  tool_category: string;
  decision: string;
  outcome: string;
  duration_ms: number;
  cost: { input_tokens: number; output_tokens: number; latency_ms: number };
  events: string[];
}

export interface TimelineApproval {
  request_id: string;
  action: string;
  risk_tier: string;
  decision: Record<string, string>;
  status: string;
  grant_id?: string | null;
  consumed_at?: string | null;
  decision_actor?: string | null;
}

export interface TimelineValidation {
  ran: boolean;
  summary: string;
}

export type { TimelineSafetyInvariants, SafetyInvariantValue } from "@/lib/timeline/safety";

export interface RunTimeline {
  timeline_schema_version: number;
  run_id: string;
  tenant_id: string;
  task_type: string;
  status: string;
  actor: { actor_id: string; roles: string[] };
  policy_snapshot_id: string;
  summary: string;
  started_at: string;
  ended_at: string | null;
  duration_ms: number;
  nodes: TimelineNode[];
  citations: TimelineCitation[];
  tool_calls: TimelineToolCall[];
  approvals: TimelineApproval[];
  validation: TimelineValidation;
  proposals: Array<{ kind: string; ref: string }>;
  costs: Record<string, unknown>;
  safety_invariants: TimelineSafetyInvariants;
  failures: Array<Record<string, string>>;
}

export interface TimelineEvent {
  event_type: string;
  timestamp: string;
  summary?: string;
}

export interface TimelineApiResponse {
  run_id: string;
  events: TimelineEvent[];
  safety_invariants?: SafetyInvariantApiPayload;
}

export interface TraceEvent {
  event_type: string;
  timestamp: string;
}

export interface TraceApiResponse {
  run_id: string;
  redaction_profile: string;
  events: TraceEvent[];
}
