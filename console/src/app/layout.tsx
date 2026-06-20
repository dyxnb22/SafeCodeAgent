/**
 * Operator Console 根布局。
 * 职责：包裹全站 HTML 结构，注入全局样式与 AuthProvider（会话上下文）。
 * 不直接调用 Team Server API；认证状态由子树中的页面/组件按需发起请求。
 */
import type { ReactNode } from "react";

import { AuthProvider } from "@/components/AuthProvider";

import "./globals.css";

export const metadata = {
  title: "SafeCode Enterprise Console",
  description: "Operator console for SafeCodeAgent Enterprise",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
