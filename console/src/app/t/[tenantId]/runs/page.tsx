/**
 * 租户 Run 列表页，路由：/t/[tenantId]/runs。
 * 通过 listRuns(session) 调用 Team Server GET /runs（Bearer + 会话内租户）。
 * ProtectedShell 保证 URL tenantId 与会话一致；详情链至同租户下的 /runs/[runId]。
 */
"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { ProtectedShell } from "@/components/ProtectedShell";
import { useAuth } from "@/components/AuthProvider";
import { listRuns, type RunSummary } from "@/lib/api/runs";
import { ApiError } from "@/lib/api/client";
import { tenantScopedPath } from "@/lib/tenant/guards";

export default function TenantRunsPage() {
  const { session } = useAuth();
  const params = useParams<{ tenantId: string }>();
  const tenantId = params.tenantId;
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!session) {
      return;
    }
    let cancelled = false;
    setLoading(true);
    // Bearer 会话驱动 Team Server runs 列表 API
    listRuns(session)
      .then((payload) => {
        if (!cancelled) {
          setRuns(payload.items);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? `Failed to load runs (${err.status})` : "Failed to load runs");
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
        <h1>Runs</h1>
        {loading ? <p className="muted">Loading runs…</p> : null}
        {error ? <p className="forbidden">{error}</p> : null}
        {!loading && !error && runs.length === 0 ? <p className="muted">No runs found.</p> : null}
        {runs.length > 0 ? (
          <table>
            <thead>
              <tr>
                <th>Run ID</th>
                <th>Task</th>
                <th>Status</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.run_id}>
                  <td>
                    <Link href={tenantScopedPath(tenantId, `/runs/${encodeURIComponent(run.run_id)}`)}>
                      {run.run_id}
                    </Link>
                  </td>
                  <td>{run.task_type}</td>
                  <td>{run.status}</td>
                  <td>{run.updated_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </main>
    </ProtectedShell>
  );
}
