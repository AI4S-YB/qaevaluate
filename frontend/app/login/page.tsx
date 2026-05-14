"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import { loadSession, saveSession, type AuthSession } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const session = loadSession();
    if (session) {
      router.replace(session.user.role === "admin" ? "/admin" : "/expert");
    }
  }, [router]);

  async function handleLogin() {
    setSubmitting(true);
    setError(null);
    try {
      const session = await apiFetch<AuthSession>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password })
      });
      saveSession(session);
      router.push(session.user.role === "admin" ? "/admin" : "/expert");
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen bg-background bg-mesh px-4 py-6 lg:px-6">
      <div className="mx-auto max-w-xl">
        <Card>
          <CardHeader>
            <p className="text-sm text-muted-foreground">登录</p>
            <CardTitle className="text-3xl">进入 QA 评测工作台</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {error ? (
              <div className="rounded-[24px] border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
                {error}
              </div>
            ) : null}
            <input
              className="field"
              placeholder="用户名"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
            />
            <input
              className="field"
              placeholder="密码"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            <div className="flex items-center justify-between">
              <Link className="text-sm text-muted-foreground hover:text-foreground" href="/register">
                还没有账号，去注册
              </Link>
              <Button disabled={submitting} onClick={() => void handleLogin()}>
                {submitting ? "登录中…" : "登录"}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
