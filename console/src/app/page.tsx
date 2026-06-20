/**
 * 公开首页（未登录可访问）。
 * 职责：介绍 Console 并引导至 /login；不承载租户路由（/t/[tenantId]/…）。
 * Team Server API 在此页不发起调用。
 */
import Link from "next/link";

export default function HomePage() {
  return (
    <main>
      <h1>SafeCode Enterprise Console</h1>
      <p className="muted">Governed operator surface for the Team Server API.</p>
      <p>
        <Link href="/login">Sign in</Link>
      </p>
    </main>
  );
}
