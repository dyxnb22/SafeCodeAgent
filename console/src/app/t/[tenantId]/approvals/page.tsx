/**
 * 审批收件箱，路由：/t/[tenantId]/approvals。
 * 调用 Team Server listApprovals(session, { status: "pending" }) 拉取待决项；
 * ApprovalList 展示摘要表，每项下方 ApprovalDecideForm 供操作员批准/拒绝（含 rationale）。
 * 决策成功后仅更新本地列表状态，不自动刷新全量列表。
 */
"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { ProtectedShell } from "@/components/ProtectedShell";
import { useAuth } from "@/components/AuthProvider";
import { ApprovalDecideForm } from "@/components/approvals/ApprovalDecideForm";
import { ApprovalList } from "@/components/approvals/ApprovalList";
import { listApprovals, type ApprovalSummary } from "@/lib/api/approvals";
import { ApiError } from "@/lib/api/client";

export default function ApprovalsPage() {
  const { session } = useAuth();
  const params = useParams<{ tenantId: string }>();
  const tenantId = params.tenantId;
  const [items, setItems] = useState<ApprovalSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!session) {
      return;
    }
    let cancelled = false;
    setLoading(true);
    // 仅拉取 pending，与审批收件箱语义一致
    listApprovals(session, { status: "pending" })
      .then((payload) => {
        if (!cancelled) {
          setItems(payload.items);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? `Failed to load approvals (${err.status})` : "Failed to load approvals");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [session]);

  return (
    <ProtectedShell>
      <main>
        <h1>Approval Inbox</h1>
        {loading ? <p className="muted">Loading pending approvals…</p> : null}
        {error ? <p className="forbidden">{error}</p> : null}
        <ApprovalList items={items} tenantId={tenantId} />
        {session
          ? items.map((approval) => (
              <div key={approval.approval_id} style={{ marginTop: "1rem", borderTop: "1px solid #ddd" }}>
                <h2>{approval.approval_id}</h2>
                <ApprovalDecideForm
                  approval={approval}
                  session={session}
                  onDecided={(status) => {
                    setItems((current) =>
                      current.map((item) =>
                        item.approval_id === approval.approval_id ? { ...item, status } : item,
                      ),
                    );
                  }}
                />
              </div>
            ))
          : null}
      </main>
    </ProtectedShell>
  );
}
