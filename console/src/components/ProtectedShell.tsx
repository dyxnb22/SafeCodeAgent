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
