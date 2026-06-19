"use client";

/** Cost summary from timeline costs block (v2.3.4). */

export function CostSummary({ costs }: { costs: Record<string, unknown> }) {
  const total = (costs.total as Record<string, number> | undefined) ?? {};
  const byNode = (costs.by_node as Record<string, Record<string, number>> | undefined) ?? {};
  const nodeCount = Object.keys(byNode).length;
  const inputTokens = total.input_tokens ?? 0;
  const outputTokens = total.output_tokens ?? 0;
  const latencyMs = total.latency_ms ?? 0;

  return (
    <section aria-label="Cost summary" style={{ marginBottom: "1rem" }}>
      <h2>Cost Summary</h2>
      <ul>
        <li>Input tokens: {inputTokens}</li>
        <li>Output tokens: {outputTokens}</li>
        <li>Total latency: {latencyMs} ms</li>
        <li>Nodes with cost data: {nodeCount}</li>
      </ul>
    </section>
  );
}
