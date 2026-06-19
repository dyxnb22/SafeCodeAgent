"use client";

import { ProtectedShell } from "@/components/ProtectedShell";

export default function TenantRunsPlaceholderPage() {
  return (
    <ProtectedShell>
      <main>
        <h1>Runs</h1>
        <p className="muted">Run list loads in v2.3.2.</p>
      </main>
    </ProtectedShell>
  );
}
