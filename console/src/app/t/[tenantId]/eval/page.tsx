"use client";

import { useEffect, useState } from "react";

import { ProtectedShell } from "@/components/ProtectedShell";
import { useAuth } from "@/components/AuthProvider";
import { listEvalBaselines, type EvalBaselineSummary } from "@/lib/api/eval";
import { ApiError } from "@/lib/api/client";

export default function EvalPage() {
  const { session } = useAuth();
  const [items, setItems] = useState<EvalBaselineSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!session) {
      return;
    }
    let cancelled = false;
    setLoading(true);
    listEvalBaselines(session)
      .then((payload) => {
        if (!cancelled) {
          setItems(payload.items);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? `Failed to load baselines (${err.status})` : "Failed to load baselines");
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
        <h1>Eval baselines</h1>
        <p className="muted">Read-only view of checked-in regression baselines.</p>
        {loading ? <p className="muted">Loading baselines…</p> : null}
        {error ? <p className="forbidden">{error}</p> : null}
        {!loading && !error && items.length === 0 ? <p className="muted">No baselines found.</p> : null}
        {items.length > 0 ? (
          <table>
            <thead>
              <tr>
                <th>Suite</th>
                <th>Baseline ID</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.baseline_id}>
                  <td>{item.suite}</td>
                  <td>{item.baseline_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </main>
    </ProtectedShell>
  );
}
