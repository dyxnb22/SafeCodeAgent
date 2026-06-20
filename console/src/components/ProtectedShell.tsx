/**
 * 租户作用域页面的认证/授权外壳。
 * 职责：
 * - 未登录 → 重定向 /login；
 * - URL 中 [tenantId] 与会话 tenantId 不一致 → 禁止跨租户访问；
 * - 通过时渲染顶栏导航（Runs / Approvals / Eval），链接均带 /t/{tenantId} 前缀。
 * 本身不调用 Team Server API，仅消费 useAuth 会话与路由参数。
 */
"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { useAuth } from "@/components/AuthProvider";
import { evaluateTenantAccess } from "@/lib/tenant/guards";

export function ProtectedShell({ children }: { children: ReactNode }) {
  const { session } = useAuth();
  const router = useRouter();
  const params = useParams<{ tenantId?: string }>();
  const routeTenant = typeof params?.tenantId === "string" ? params.tenantId : null;
  // 比对 URL [tenantId] 与会话 tenantId，防止跨租户越权
  const verdict = evaluateTenantAccess(session, routeTenant);

  useEffect(() => {
    if (verdict === "unauthenticated") {
      router.replace("/login");
    }
  }, [router, verdict]);

  if (verdict === "unauthenticated") {
    return <p>Redirecting to login…</p>;
  }

  if (verdict === "tenant_mismatch") {
    return (
      <main>
        <h1>Forbidden</h1>
        <p>Cross-tenant access is not allowed.</p>
      </main>
    );
  }

  return (
    <div>
      <header style={{ display: "flex", gap: "1rem", marginBottom: "1rem" }}>
        <strong>SafeCode Console</strong>
        <span>Tenant: {session?.tenantId}</span>
        <Link href={`/t/${encodeURIComponent(session!.tenantId)}/runs`}>Runs</Link>
        <Link href={`/t/${encodeURIComponent(session!.tenantId)}/approvals`}>Approvals</Link>
        <Link href={`/t/${encodeURIComponent(session!.tenantId)}/eval`}>Eval</Link>
      </header>
      {children}
    </div>
  );
}
