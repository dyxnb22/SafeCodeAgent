/**
 * Run 原始追踪事件只读视图。
 * 数据来自 Team Server getRunTrace；展示事件类型/时间戳及经脱敏的 JSON 详情。
 * redaction_profile 标明服务端应用的脱敏配置，与审计/合规导出一致。
 */
"use client";

import type { TraceApiResponse } from "@/components/timeline/types";
import { serializeForDisplay } from "@/lib/redaction/display";

export function TraceEventsView({ trace }: { trace: TraceApiResponse }) {
  return (
    <div>
      <p className="muted">Redaction profile: {trace.redaction_profile}</p>
      {trace.events.length === 0 ? (
        <p className="muted">No trace events recorded.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Event type</th>
              <th>Timestamp</th>
            </tr>
          </thead>
          <tbody>
            {trace.events.map((event, index) => (
              <tr key={`${event.event_type}-${event.timestamp}-${index}`}>
                <td>{event.event_type}</td>
                <td>{event.timestamp}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <details style={{ marginTop: "1rem" }}>
        <summary>Redacted JSON</summary>
        <pre>{serializeForDisplay(trace)}</pre>
      </details>
    </div>
  );
}
