/** Run list and detail API helpers (v2.3.2). */

import { createApiClient } from "@/lib/api/client";
import type { RunTimeline, TimelineApiResponse, TraceApiResponse } from "@/components/timeline/types";
import type { ConsoleSession } from "@/lib/auth/session";

export interface RunSummary {
  run_id: string;
  tenant_id: string;
  task_type: string;
  status: string;
  created_at: string;
  updated_at: string;
  status_url?: string;
}

export interface RunListResponse {
  items: RunSummary[];
  next_cursor?: string;
}

export async function listRuns(
  session: ConsoleSession,
  opts?: { status?: string; cursor?: string },
): Promise<RunListResponse> {
  const client = createApiClient(session);
  return client.get<RunListResponse>("/v2/runs", {
    status: opts?.status,
    cursor: opts?.cursor,
  });
}

export async function getRun(session: ConsoleSession, runId: string): Promise<RunSummary> {
  const client = createApiClient(session);
  return client.get<RunSummary>(`/v2/runs/${encodeURIComponent(runId)}`);
}

export async function getRunTimeline(
  session: ConsoleSession,
  runId: string,
): Promise<TimelineApiResponse> {
  const client = createApiClient(session);
  return client.get<TimelineApiResponse>(`/v2/runs/${encodeURIComponent(runId)}/timeline`);
}

export async function getRunTrace(
  session: ConsoleSession,
  runId: string,
): Promise<TraceApiResponse> {
  const client = createApiClient(session);
  return client.get<TraceApiResponse>(`/v2/runs/${encodeURIComponent(runId)}/trace`);
}

export function timelineFromApi(run: RunSummary, timeline: TimelineApiResponse): RunTimeline {
  const nodes = timeline.events.map((event) => ({
    name: event.event_type,
    status: "completed",
    started_at: event.timestamp,
    ended_at: event.timestamp,
    duration_ms: 0,
    summary: event.summary ?? event.event_type,
    events: [],
    artifacts: [],
  }));

  return {
    timeline_schema_version: 1,
    run_id: timeline.run_id,
    tenant_id: run.tenant_id,
    task_type: run.task_type,
    status: run.status,
    actor: { actor_id: "unknown", roles: [] },
    policy_snapshot_id: "n/a",
    summary: `${run.task_type} run ${run.run_id}`,
    started_at: run.created_at,
    ended_at: run.updated_at,
    duration_ms: 0,
    nodes,
    citations: [],
    tool_calls: [],
    approvals: [],
    validation: { ran: false, summary: "n/a" },
    proposals: [],
    costs: {},
    safety_invariants: {
      audit_chain_intact: true,
      no_unauthorized_mutation: true,
      no_policy_block_overridden: true,
      no_grant_double_consume: true,
      redaction_complete: true,
    },
    failures: [],
  };
}
