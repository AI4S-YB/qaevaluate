"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import { clearSession, loadSession, type AuthSession } from "@/lib/auth";
import { Button } from "@/components/ui/button";

export function AuthStatus() {
  const pathname = usePathname();
  const router = useRouter();
  const [session, setSession] = useState<AuthSession | null>(null);

  useEffect(() => {
    setSession(loadSession());
  }, [pathname]);

  if (!session) {
    return (
      <div className="flex items-center gap-3">
        <Link className="text-sm text-muted-foreground hover:text-foreground" href="/login">
          登录
        </Link>
        <Button asChild size="sm">
          <Link href="/register">注册</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3">
      <div className="text-right">
        <p className="text-sm font-medium">{session.user.username}</p>
        <p className="text-xs text-muted-foreground">
          {session.user.role === "admin" ? "管理员" : "专家"} / {session.user.status}
        </p>
      </div>
      <Button
        size="sm"
        variant="secondary"
        onClick={async () => {
          try {
            await apiFetch("/api/auth/logout", { method: "POST" });
          } catch {
            // Ignore logout transport errors and clear local state anyway.
          }
          clearSession();
          setSession(null);
          router.push("/login");
        }}
      >
        退出
      </Button>
    </div>
  );
}
