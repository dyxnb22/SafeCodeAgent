/**
 * 待审批请求摘要表（纯展示）。
 * 数据来自父页 listApprovals；Run 列链接至租户作用域 /t/{tenantId}/runs/{run_id}。
 * 不含决策操作——由 ApprovalDecideForm 处理。
 */
"use client";

import Link from "next/link";

import type { ApprovalSummary } from "@/lib/api/approvals";
import { tenantScopedPath } from "@/lib/tenant/guards";

export function ApprovalList({
  items,
  tenantId,
}: {
  items: ApprovalSummary[];
  tenantId: string;
}) {
  if (items.length === 0) {
    return <p className="muted">No approval requests.</p>;
  }

  return (
    <table>
      <thead>
        <tr>
          <th>Approval ID</th>
          <th>Run</th>
          <th>Status</th>
          <th>Created</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.approval_id}>
            <td>{item.approval_id}</td>
            <td>
              <Link href={tenantScopedPath(tenantId, `/runs/${encodeURIComponent(item.run_id)}`)}>
                {item.run_id}
              </Link>
            </td>
            <td>{item.status}</td>
            <td>{item.created_at}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
