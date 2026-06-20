/**
 * 单条审批的决策表单（审批流程 UI 核心）。
 * 仅 status === "pending" 时显示 Rationale + Approve/Reject；
 * 调用 Team Server decideApproval(session, approvalId, decision, rationale)，
 * 成功后通过 onDecided 回调更新父组件本地状态。已决项只读展示决策结果。
 */
"use client";

import { useState } from "react";

import { decideApproval, type ApprovalSummary } from "@/lib/api/approvals";
import type { ConsoleSession } from "@/lib/auth/session";
import { ApiError } from "@/lib/api/client";

export function ApprovalDecideForm({
  approval,
  session,
  onDecided,
}: {
  approval: ApprovalSummary;
  session: ConsoleSession;
  onDecided: (status: string) => void;
}) {
  const [rationale, setRationale] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(decision: "approved" | "rejected") {
    setBusy(true);
    setError(null);
    try {
      const result = await decideApproval(session, approval.approval_id, decision, rationale);
      onDecided(result.status);
    } catch (err) {
      setError(err instanceof ApiError ? `Decision failed (${err.status})` : "Decision failed");
    } finally {
      setBusy(false);
    }
  }

  if (approval.status !== "pending") {
    return <p className="muted">Decision recorded: {approval.status}</p>;
  }

  return (
    <div style={{ marginTop: "0.5rem" }}>
      <label htmlFor={`rationale-${approval.approval_id}`}>Rationale</label>
      <textarea
        id={`rationale-${approval.approval_id}`}
        value={rationale}
        onChange={(event) => setRationale(event.target.value)}
        rows={2}
        style={{ display: "block", width: "100%", marginBottom: "0.5rem" }}
      />
      <div style={{ display: "flex", gap: "0.5rem" }}>
        <button type="button" disabled={busy} onClick={() => submit("approved")}>
          Approve
        </button>
        <button type="button" disabled={busy} onClick={() => submit("rejected")}>
          Reject
        </button>
      </div>
      {error ? <p className="forbidden">{error}</p> : null}
    </div>
  );
}
