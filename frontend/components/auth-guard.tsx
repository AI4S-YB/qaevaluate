"use client";

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

  useEffect(() => {
    const current = loadSession();
    setSession(current);

    if (!current) {
      router.replace("/login");
      return;
    }

    const allowed =
      current.user.role === role || (allowAdmin && role === "expert" && current.user.role === "admin");

    if (!allowed) {
      router.replace(current.user.role === "admin" ? "/admin" : "/expert");
    }
  }, [allowAdmin, pathname, role, router]);

  const allowed =
    session?.user.role === role ||
    (allowAdmin && role === "expert" && session?.user.role === "admin");

  if (!session || !allowed) {
    return (
      <div className="rounded-[28px] border border-border bg-stone-50 p-10 text-center text-sm text-muted-foreground">
        正在校验登录状态…
      </div>
    );
  }

  return <>{children}</>;
}
