/**
 * 单次 Run 详情页，路由：/t/[tenantId]/runs/[runId]。
 * 并行请求 Team Server：getRun、getRunTimeline、getRunTrace；
 * 展示时间线（RunTimelineView）、追踪事件（TraceEventsView）与成本摘要。
 * Evidence 导出链至同租户 /runs/[runId]/evidence。
 */
"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { ProtectedShell } from "@/components/ProtectedShell";
import { useAuth } from "@/components/AuthProvider";
import { CostSummary } from "@/components/cost/CostSummary";
import { RunTimelineView } from "@/components/timeline/RunTimelineView";
import { TraceEventsView } from "@/components/timeline/TraceEventsView";
import type { RunTimeline, TraceApiResponse } from "@/components/timeline/types";
import { ApiError } from "@/lib/api/client";
import {
  getRun,
  getRunTimeline,
  getRunTrace,
  timelineFromApi,
  type RunSummary,
} from "@/lib/api/runs";
import { tenantScopedPath } from "@/lib/tenant/guards";

type DetailTab = "timeline" | "trace";

export default function RunDetailPage() {
  const { session } = useAuth();
  const params = useParams<{ tenantId: string; runId: string }>();
  const runId = params.runId;
  const tenantId = params.tenantId;
  const [run, setRun] = useState<RunSummary | null>(null);
  const [timelineView, setTimelineView] = useState<RunTimeline | null>(null);
  const [trace, setTrace] = useState<TraceApiResponse | null>(null);
  const [tab, setTab] = useState<DetailTab>("timeline");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!session || !runId) {
      return;
    }
    let cancelled = false;
    setLoading(true);
    // 并行拉取 Run 元数据、结构化时间线与原始 trace
    Promise.all([getRun(session, runId), getRunTimeline(session, runId), getRunTrace(session, runId)])
      .then(([runSummary, timelineResponse, traceResponse]) => {
        if (!cancelled) {
          setRun(runSummary);
          setTimelineView(timelineFromApi(runSummary, timelineResponse));
          setTrace(traceResponse);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? `Failed to load run (${err.status})` : "Failed to load run");
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
  }, [session, runId]);

  return (
    <ProtectedShell>
      <main>
        <p>
          <Link href={tenantScopedPath(tenantId, "/runs")}>← Runs</Link>
          {" · "}
          <Link href={tenantScopedPath(tenantId, `/runs/${encodeURIComponent(runId)}/evidence`)}>
            Evidence
          </Link>
        </p>
        <h1>Run {runId}</h1>
        {loading ? <p className="muted">Loading run…</p> : null}
        {error ? <p className="forbidden">{error}</p> : null}
        {run ? (
          <>
            <p>
              {run.task_type} · {run.status} · updated {run.updated_at}
            </p>
            {timelineView ? <CostSummary costs={timelineView.costs} /> : null}
            <div style={{ display: "flex", gap: "0.75rem", margin: "1rem 0" }}>
              <button type="button" onClick={() => setTab("timeline")} disabled={tab === "timeline"}>
                Timeline
              </button>
              <button type="button" onClick={() => setTab("trace")} disabled={tab === "trace"}>
                Trace
              </button>
            </div>
            {tab === "timeline" && timelineView ? <RunTimelineView timeline={timelineView} /> : null}
            {tab === "trace" && trace ? <TraceEventsView trace={trace} /> : null}
          </>
        ) : null}
      </main>
    </ProtectedShell>
  );
}
