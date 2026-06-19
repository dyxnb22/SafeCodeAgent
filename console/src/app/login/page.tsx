"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { tokenAppearsInUrl } from "@/lib/auth/claims";
import { buildAuthorizationUrl, generatePkcePair } from "@/lib/auth/oidc";
import { tenantScopedPath } from "@/lib/tenant/guards";

export default function LoginPage() {
  const { loginWithAccessToken, session } = useAuth();
  const router = useRouter();
  const [tokenInput, setTokenInput] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (session) {
      router.replace(tenantScopedPath(session.tenantId, "/runs"));
    }
  }, [router, session]);

  async function startOidc() {
    setError(null);
    try {
      const state = crypto.randomUUID();
      const pkce = await generatePkcePair();
      sessionStorage.setItem("safecode-oidc-state", state);
      sessionStorage.setItem("safecode-oidc-verifier", pkce.verifier);
      const url = buildAuthorizationUrl({ state, pkceChallenge: pkce.challenge });
      if (tokenAppearsInUrl(url)) {
        throw new Error("oidc URL must not embed bearer tokens");
      }
      window.location.assign(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "oidc start failed");
    }
  }

  function submitDevToken() {
    setError(null);
    try {
      if (tokenAppearsInUrl(tokenInput)) {
        throw new Error("paste the token only in the form field, not the URL");
      }
      loginWithAccessToken(tokenInput.trim());
      const nextSession = JSON.parse(sessionStorage.getItem("safecode-console-session") || "{}");
      router.push(tenantScopedPath(nextSession.tenantId, "/runs"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "login failed");
    }
  }

  return (
    <main>
      <h1>Sign in</h1>
      <p className="muted">OIDC bearer session is stored in sessionStorage only.</p>
      <button type="button" onClick={() => void startOidc()}>
        Continue with OIDC
      </button>
      <hr />
      <label htmlFor="dev-token">Development bearer token</label>
      <textarea
        id="dev-token"
        rows={4}
        value={tokenInput}
        onChange={(event) => setTokenInput(event.target.value)}
        style={{ display: "block", width: "100%", marginTop: "0.5rem" }}
      />
      <button type="button" onClick={submitDevToken} style={{ marginTop: "0.5rem" }}>
        Use development token
      </button>
      {error ? <p className="forbidden">{error}</p> : null}
    </main>
  );
}
