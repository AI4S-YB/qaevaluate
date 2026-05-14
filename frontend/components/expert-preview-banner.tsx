"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { loadSession, type AuthSession } from "@/lib/auth";

export function ExpertPreviewBanner() {
  const pathname = usePathname();
  const [session, setSession] = useState<AuthSession | null>(null);

  useEffect(() => {
    setSession(loadSession());
  }, [pathname]);

  if (session?.user.role !== "admin") {
    return null;
  }

  return (
    <div className="mb-6 rounded-[24px] border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-7 text-amber-900">
      当前为管理员预览模式。你正在以管理员身份查看专家端页面，系统已自动分配一批预览任务用于查看流程与问题内容。
    </div>
  );
}
