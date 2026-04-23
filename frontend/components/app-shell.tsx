import type { Route } from "next";
import Link from "next/link";
import { type ReactNode } from "react";

import { AuthStatus } from "@/components/auth-status";
import { cn } from "@/lib/utils";

export type NavItem = {
  href: Route;
  label: string;
  hint: string;
};

type AppShellProps = {
  title: string;
  subtitle: string;
  navItems: NavItem[];
  children: ReactNode;
  roleLabel: string;
};

export function AppShell({
  title,
  subtitle,
  navItems,
  children,
  roleLabel
}: AppShellProps) {
  return (
    <div className="min-h-screen bg-background bg-mesh text-foreground">
      <div className="mx-auto flex min-h-screen max-w-[1600px] gap-6 px-4 py-5 lg:px-6">
        <aside className="hidden w-[280px] shrink-0 rounded-[14px] border border-white/70 bg-white/85 p-6 shadow-soft lg:block">
          <div className="mb-8 space-y-2">
            <span className="inline-flex rounded-md bg-accent px-3 py-1 text-xs font-medium text-accent-foreground">
              {roleLabel}
            </span>
            <div>
              <h1 className="font-serif text-3xl font-semibold">{title}</h1>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                {subtitle}
              </p>
            </div>
          </div>
          <nav className="space-y-2">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "block rounded-md border border-transparent px-4 py-3 transition",
                  "hover:border-border hover:bg-stone-50"
                )}
              >
                <div className="font-medium">{item.label}</div>
                <div className="text-xs text-muted-foreground">{item.hint}</div>
              </Link>
            ))}
          </nav>
        </aside>
        <main className="flex-1">
          <div className="rounded-[14px] border border-white/70 bg-white/80 p-5 shadow-soft backdrop-blur lg:p-8">
            <div className="mb-6 flex items-center justify-end">
              <AuthStatus />
            </div>
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
