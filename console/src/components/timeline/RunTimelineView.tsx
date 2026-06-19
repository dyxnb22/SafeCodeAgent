"use client";

import type { ReactNode } from "react";

import { TIMELINE_SECTION_ORDER } from "@/components/timeline/sections";
import type { RunTimeline } from "@/components/timeline/types";
import { redactFieldForDisplay } from "@/lib/redaction/display";
import {
  formatSafetyInvariantDisplay,
  type TimelineSafetyInvariants,
} from "@/lib/timeline/safety";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section style={{ marginBottom: "1.5rem" }}>
      <h2>{title}</h2>
      {children}
    </section>
  );
}

function SummarySection({ timeline }: { timeline: RunTimeline }) {
  const total = (timeline.costs.total as Record<string, number> | undefined) ?? {};
  return (
    <Section title={TIMELINE_SECTION_ORDER[0]}>
      <ul>
        <li>Run ID: {timeline.run_id}</li>
        <li>Tenant: {timeline.tenant_id}</li>
        <li>Task: {timeline.task_type}</li>
        <li>
          Actor: {timeline.actor.actor_id} (roles: {timeline.actor.roles.join(", ") || "none"})
        </li>
        <li>Policy snapshot: {timeline.policy_snapshot_id}</li>
        <li>Status: {timeline.status}</li>
        <li>Started: {timeline.started_at}</li>
        <li>Ended: {timeline.ended_at ?? "n/a"}</li>
        <li>Duration: {timeline.duration_ms} ms</li>
        <li>
          Total cost: {total.input_tokens ?? 0} in / {total.output_tokens ?? 0} out tokens
        </li>
      </ul>
    </Section>
  );
}

function TimelineNodesSection({ timeline }: { timeline: RunTimeline }) {
  return (
    <Section title={TIMELINE_SECTION_ORDER[1]}>
      {timeline.nodes.length === 0 ? (
        <p className="muted">No timeline nodes recorded.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Node</th>
              <th>Status</th>
              <th>Duration (ms)</th>
              <th>Summary</th>
            </tr>
          </thead>
          <tbody>
            {timeline.nodes.map((node) => (
              <tr key={`${node.name}-${node.started_at}`}>
                <td>{node.name}</td>
                <td>{node.status}</td>
                <td>{node.duration_ms}</td>
                <td>{redactFieldForDisplay("summary", node.summary)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Section>
  );
}

function CitationsSection({ timeline }: { timeline: RunTimeline }) {
  return (
    <Section title={TIMELINE_SECTION_ORDER[2]}>
      {timeline.citations.length === 0 ? (
        <p className="muted">No citations recorded.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Path</th>
              <th>Lines</th>
              <th>Score</th>
              <th>Permission</th>
              <th>Freshness</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {timeline.citations.map((cite) => (
              <tr key={cite.citation_id}>
                <td>{cite.path}</td>
                <td>
                  {cite.start_line}-{cite.end_line}
                </td>
                <td>{cite.score.toFixed(2)}</td>
                <td>{cite.permission_verdict}</td>
                <td>{cite.freshness}</td>
                <td>{cite.selection_reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Section>
  );
}

function ToolCallsSection({ timeline }: { timeline: RunTimeline }) {
  return (
    <Section title={TIMELINE_SECTION_ORDER[3]}>
      {timeline.tool_calls.length === 0 ? (
        <p className="muted">No tool calls recorded.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Tool</th>
              <th>Category</th>
              <th>Decision</th>
              <th>Outcome</th>
              <th>Duration (ms)</th>
            </tr>
          </thead>
          <tbody>
            {timeline.tool_calls.map((call) => (
              <tr key={call.call_id}>
                <td>{call.tool_name}</td>
                <td>{call.tool_category}</td>
                <td>{call.decision}</td>
                <td>{call.outcome}</td>
                <td>{call.duration_ms}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Section>
  );
}

function ApprovalsSection({ timeline }: { timeline: RunTimeline }) {
  return (
    <Section title={TIMELINE_SECTION_ORDER[4]}>
      {timeline.approvals.length === 0 ? (
        <p className="muted">No approvals recorded.</p>
      ) : (
        <ul>
          {timeline.approvals.map((approval) => (
            <li key={approval.request_id}>
              <strong>{approval.action}</strong> ({approval.risk_tier}): {approval.status} —{" "}
              {approval.decision.reason ?? ""}
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

function ValidationSection({ timeline }: { timeline: RunTimeline }) {
  return (
    <Section title={TIMELINE_SECTION_ORDER[5]}>
      <ul>
        <li>Ran: {String(timeline.validation.ran)}</li>
        <li>Summary: {timeline.validation.summary}</li>
      </ul>
    </Section>
  );
}

function CostSection({ timeline }: { timeline: RunTimeline }) {
  const byNode = (timeline.costs.by_node as Record<string, Record<string, number>> | undefined) ?? {};
  const entries = Object.entries(byNode);
  return (
    <Section title={TIMELINE_SECTION_ORDER[6]}>
      {entries.length === 0 ? (
        <p className="muted">No per-node cost breakdown.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Node</th>
              <th>Input</th>
              <th>Output</th>
              <th>Latency (ms)</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([nodeName, cost]) => (
              <tr key={nodeName}>
                <td>{nodeName}</td>
                <td>{cost.input_tokens ?? 0}</td>
                <td>{cost.output_tokens ?? 0}</td>
                <td>{cost.latency_ms ?? 0}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Section>
  );
}

function SafetySection({ timeline }: { timeline: RunTimeline }) {
  const inv = timeline.safety_invariants;
  const checks: Array<[string, keyof TimelineSafetyInvariants]> = [
    ["Audit chain intact", "audit_chain_intact"],
    ["No unauthorized mutation", "no_unauthorized_mutation"],
    ["No policy block overridden", "no_policy_block_overridden"],
    ["No grant double-consume", "no_grant_double_consume"],
    ["Redaction complete", "redaction_complete"],
  ];
  const verifiedCount = checks.filter(([, key]) => inv[key] === true).length;
  return (
    <Section title={TIMELINE_SECTION_ORDER[7]}>
      {verifiedCount === 0 ? (
        <p className="muted">
          Safety invariants are shown only when the API returns verified values. Unverified
          indicators are not treated as passed.
        </p>
      ) : null}
      <ul>
        {checks.map(([label, key]) => {
          const display = formatSafetyInvariantDisplay(inv[key]);
          return (
            <li key={key} className={`safety-${display.tone}`}>
              <span aria-hidden="true">{display.symbol}</span> {label}{" "}
              <span className="muted">({display.detail})</span>
            </li>
          );
        })}
      </ul>
    </Section>
  );
}

function FailuresSection({ timeline }: { timeline: RunTimeline }) {
  return (
    <Section title={TIMELINE_SECTION_ORDER[8]}>
      {timeline.failures.length === 0 ? (
        <p className="muted">No failures recorded.</p>
      ) : (
        <ul>
          {timeline.failures.map((failure, index) => (
            <li key={failure.failure_id ?? `failure-${index}`}>
              <strong>{failure.category ?? "unknown"}</strong> @ {failure.node_name ?? "n/a"}:{" "}
              {redactFieldForDisplay("message", failure.message ?? "")}
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

export function RunTimelineView({ timeline }: { timeline: RunTimeline }) {
  return (
    <div>
      <SummarySection timeline={timeline} />
      <TimelineNodesSection timeline={timeline} />
      <CitationsSection timeline={timeline} />
      <ToolCallsSection timeline={timeline} />
      <ApprovalsSection timeline={timeline} />
      <ValidationSection timeline={timeline} />
      <CostSection timeline={timeline} />
      <SafetySection timeline={timeline} />
      <FailuresSection timeline={timeline} />
    </div>
  );
}

export function timelineSectionNames(): string[] {
  return [...TIMELINE_SECTION_ORDER];
}
