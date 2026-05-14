"use client";

import type { Route } from "next";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { loadSession, type AuthSession } from "@/lib/auth";

type AuthGuardProps = {
  role: "admin" | "expert";
  allowAdmin?: boolean;
  children: ReactNode;
};

export function AuthGuard({ role, allowAdmin = false, children }: AuthGuardProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [session, setSession] = useState<AuthSession | null | undefined>(undefined);
  const [redirectTarget, setRedirectTarget] = useState<string | null>(null);

  function hardRedirect(target: Route) {
    setRedirectTarget(target);
    if (typeof window !== "undefined") {
      window.location.replace(target);
      return;
    }
    router.replace(target);
  }

  useEffect(() => {
    const current = loadSession();
    setSession(current);

    if (!current) {
      hardRedirect("/login");
      return;
    }

    const allowed =
      current.user.role === role || (allowAdmin && role === "expert" && current.user.role === "admin");

    if (!allowed) {
      hardRedirect(current.user.role === "admin" ? "/admin" : "/expert");
    }
  }, [allowAdmin, pathname, role, router]);

  const allowed =
    session?.user.role === role ||
    (allowAdmin && role === "expert" && session?.user.role === "admin");
  const fallbackTarget = (redirectTarget ?? "/login") as Route;

  if (!session || !allowed) {
    return (
      <div className="space-y-3 rounded-[28px] border border-border bg-stone-50 p-10 text-center text-sm text-muted-foreground">
        <p>{redirectTarget ? "正在跳转…" : "正在校验登录状态…"}</p>
        <p className="text-xs">
          如果页面没有自动跳转，直接前往
          {" "}
          <Link className="underline underline-offset-4" href={fallbackTarget}>
            {fallbackTarget}
          </Link>
          。
        </p>
        <p className="text-xs">
          本地开发时 `localhost:3100` 和 `127.0.0.1:3100` 的登录态互不共享。
        </p>
      </div>
    );
  }

  return <>{children}</>;
}
