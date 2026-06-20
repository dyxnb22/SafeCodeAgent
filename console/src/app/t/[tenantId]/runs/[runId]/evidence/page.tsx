/**
 * Run 合规证据包只读导出页，路由：/t/[tenantId]/runs/[runId]/evidence。
 * 调用 Team Server downloadEvidence，将 zip bundle 触发浏览器下载；无写操作。
 */
"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { ProtectedShell } from "@/components/ProtectedShell";
import { useAuth } from "@/components/AuthProvider";
import { downloadEvidence } from "@/lib/api/evidence";
import { ApiError } from "@/lib/api/client";
import { tenantScopedPath } from "@/lib/tenant/guards";

export default function RunEvidencePage() {
  const { session } = useAuth();
  const params = useParams<{ tenantId: string; runId: string }>();
  const runId = params.runId;
  const tenantId = params.tenantId;
  const [status, setStatus] = useState<string>("Read-only evidence export from the Team Server.");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setStatus("Read-only evidence export from the Team Server.");
  }, [runId]);

  async function handleDownload() {
    if (!session) {
      return;
    }
    setBusy(true);
    try {
      const blob = await downloadEvidence(session, runId);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `evidence-${runId}.zip`;
      anchor.click();
      URL.revokeObjectURL(url);
      setStatus("Evidence bundle downloaded.");
    } catch (err) {
      setStatus(err instanceof ApiError ? `Export failed (${err.status})` : "Export failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <ProtectedShell>
      <main>
        <p>
          <Link href={tenantScopedPath(tenantId, `/runs/${encodeURIComponent(runId)}`)}>← Run detail</Link>
        </p>
        <h1>Evidence export</h1>
        <p className="muted">{status}</p>
        <button type="button" disabled={busy || !session} onClick={handleDownload}>
          Download evidence bundle
        </button>
      </main>
    </ProtectedShell>
  );
}
