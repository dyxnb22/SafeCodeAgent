/** Approval inbox API helpers (v2.3.3). */

import { createApiClient } from "@/lib/api/client";
import type { ConsoleSession } from "@/lib/auth/session";

export interface ApprovalSummary {
  approval_id: string;
  run_id: string;
  tenant_id: string;
  status: string;
  created_at: string;
}

export interface ApprovalListResponse {
  items: ApprovalSummary[];
}

export interface ApprovalDecisionResponse {
  approval_id: string;
  status: string;
}

export async function listApprovals(
  session: ConsoleSession,
  opts?: { status?: string },
): Promise<ApprovalListResponse> {
  const client = createApiClient(session);
  return client.get<ApprovalListResponse>("/v2/approvals", { status: opts?.status });
}

export function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `console-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export async function decideApproval(
  session: ConsoleSession,
  approvalId: string,
  decision: "approved" | "rejected",
  rationale: string,
): Promise<ApprovalDecisionResponse> {
  const client = createApiClient(session);
  return client.post<ApprovalDecisionResponse>(
    `/v2/approvals/${encodeURIComponent(approvalId)}/decide`,
    { decision, rationale },
    { idempotencyKey: newIdempotencyKey() },
  );
}
