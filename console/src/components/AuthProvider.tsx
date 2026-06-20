/**
 * 全站认证上下文：ConsoleSession（含 tenantId、Bearer token）的读写与登出。
 * 会话持久化在浏览器 sessionStorage；后续 lib/api/* 请求携带 token 调用 Team Server API。
 * 不执行租户路由校验——由 ProtectedShell 与 evaluateTenantAccess 负责。
 */
"use client";

import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

import {
  createSessionStore,
  isAuthenticated,
  sessionFromAccessToken,
  type ConsoleSession,
} from "@/lib/auth/session";

interface AuthContextValue {
  session: ConsoleSession | null;
  loginWithAccessToken: (token: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

// SSR 时使用空存储桩，避免访问 window；客户端挂载后使用 sessionStorage
function browserSessionStore() {
  if (typeof window === "undefined") {
    return createSessionStore({
      getItem: () => null,
      setItem: () => undefined,
      removeItem: () => undefined,
    });
  }
  return createSessionStore(window.sessionStorage);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const store = useMemo(() => browserSessionStore(), []);
  const [session, setSession] = useState<ConsoleSession | null>(() => store.get());

  const value = useMemo<AuthContextValue>(
    () => ({
      session: isAuthenticated(session) ? session : null,
      loginWithAccessToken(token: string) {
        const next = sessionFromAccessToken(token);
        store.set(next);
        setSession(next);
      },
      logout() {
        store.clear();
        setSession(null);
      },
    }),
    [session, store],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
