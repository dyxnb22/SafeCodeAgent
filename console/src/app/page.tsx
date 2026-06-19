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
