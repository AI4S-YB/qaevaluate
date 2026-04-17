"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { loadSession, type AuthSession } from "@/lib/auth";

type AuthGuardProps = {
  role: "admin" | "expert";
  children: ReactNode;
};

export function AuthGuard({ role, children }: AuthGuardProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [session, setSession] = useState<AuthSession | null | undefined>(undefined);

  useEffect(() => {
    const current = loadSession();
    setSession(current);

    if (!current) {
      router.replace("/login");
      return;
    }

    if (current.user.role !== role) {
      router.replace(current.user.role === "admin" ? "/admin" : "/expert");
    }
  }, [pathname, role, router]);

  if (!session || session.user.role !== role) {
    return (
      <div className="rounded-[28px] border border-border bg-stone-50 p-10 text-center text-sm text-muted-foreground">
        正在校验登录状态…
      </div>
    );
  }

  return <>{children}</>;
}
