/** OIDC authorization helpers (v2.3.1). */

import { loadConsoleConfig } from "@/lib/config";

export interface PkcePair {
  verifier: string;
  challenge: string;
}

export async function generatePkcePair(): Promise<PkcePair> {
  const verifier = randomUrlSafeString(64);
  const challenge = await sha256Base64Url(verifier);
  return { verifier, challenge };
}

export function buildAuthorizationUrl(params: {
  state: string;
  pkceChallenge: string;
  config?: ReturnType<typeof loadConsoleConfig>;
}): string {
  const config = params.config ?? loadConsoleConfig();
  const url = new URL(`${config.oidcIssuer}/authorize`);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("client_id", config.oidcClientId);
  url.searchParams.set("redirect_uri", config.oidcRedirectUri);
  url.searchParams.set("scope", "openid profile email");
  url.searchParams.set("state", params.state);
  url.searchParams.set("code_challenge", params.pkceChallenge);
  url.searchParams.set("code_challenge_method", "S256");
  url.searchParams.set("audience", config.oidcAudience);
  return url.toString();
}

export function validateOidcCallbackQuery(query: URLSearchParams): { code: string; state: string } {
  if (query.get("error")) {
    throw new Error(`oidc error: ${query.get("error")}`);
  }
  if (query.has("access_token") || query.has("id_token")) {
    throw new Error("implicit tokens in callback URL are not allowed");
  }
  const code = query.get("code");
  const state = query.get("state");
  if (!code || !state) {
    throw new Error("missing oidc callback parameters");
  }
  return { code, state };
}

function randomUrlSafeString(length: number): string {
  const bytes = new Uint8Array(length);
  crypto.getRandomValues(bytes);
  return bytesToBase64Url(bytes).slice(0, length);
}

async function sha256Base64Url(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return bytesToBase64Url(new Uint8Array(digest));
}

function bytesToBase64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
