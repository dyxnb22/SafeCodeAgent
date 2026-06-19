/** Console runtime configuration (v2.3.1). */

export interface ConsoleConfig {
  apiBaseUrl: string;
  oidcIssuer: string;
  oidcAudience: string;
  oidcClientId: string;
  oidcRedirectUri: string;
}

const DEFAULT_API = "http://127.0.0.1:8080";

export function loadConsoleConfig(env: Record<string, string | undefined> = {}): ConsoleConfig {
  const apiBaseUrl = (env.NEXT_PUBLIC_SAC_API_BASE_URL || DEFAULT_API).replace(/\/$/, "");
  const oidcIssuer = (env.NEXT_PUBLIC_SAC_OIDC_ISSUER || "https://issuer.example").replace(/\/$/, "");
  const oidcAudience = env.NEXT_PUBLIC_SAC_OIDC_AUDIENCE || "safecode-enterprise";
  const oidcClientId = env.NEXT_PUBLIC_SAC_OIDC_CLIENT_ID || "safecode-console";
  const oidcRedirectUri =
    env.NEXT_PUBLIC_SAC_OIDC_REDIRECT_URI || "http://127.0.0.1:3000/login/callback";
  return { apiBaseUrl, oidcIssuer, oidcAudience, oidcClientId, oidcRedirectUri };
}
