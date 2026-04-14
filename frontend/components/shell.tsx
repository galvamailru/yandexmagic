"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Megaphone, Sparkles, Shield } from "lucide-react";
import { cn } from "@/lib/utils";

const nav = [
  { href: "/dashboard", label: "Дашборд", icon: LayoutDashboard },
  { href: "/campaigns", label: "Кампании", icon: Megaphone },
  { href: "/wizard", label: "Новая кампания", icon: Sparkles },
];

export function Shell({
  children,
  isAdmin,
}: {
  children: React.ReactNode;
  isAdmin?: boolean;
}) {
  const path = usePathname();
  return (
    <div className="min-h-screen flex">
      <aside className="w-64 border-r border-[hsl(var(--border))] bg-white p-4 flex flex-col gap-6">
        <div>
          <div className="text-xs uppercase tracking-wider text-[hsl(var(--muted-foreground))]">YandexMagic</div>
          <div className="text-lg font-semibold">AI для Директа</div>
        </div>
        <nav className="flex flex-col gap-1">
          {nav.map((n) => {
            const Icon = n.icon;
            const active = path === n.href;
            return (
              <Link
                key={n.href}
                href={n.href}
                className={cn(
                  "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium",
                  active ? "bg-[hsl(var(--muted))] text-[hsl(var(--foreground))]" : "text-[hsl(var(--muted-foreground))] hover:bg-[hsl(var(--muted))]"
                )}
              >
                <Icon className="h-4 w-4" />
                {n.label}
              </Link>
            );
          })}
          {isAdmin && (
            <Link
              href="/admin"
              className={cn(
                "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium",
                path === "/admin" ? "bg-[hsl(var(--muted))]" : "text-[hsl(var(--muted-foreground))] hover:bg-[hsl(var(--muted))]"
              )}
            >
              <Shield className="h-4 w-4" />
              Админ
            </Link>
          )}
        </nav>
      </aside>
      <main className="flex-1 p-8 bg-gradient-to-br from-slate-50 to-white">{children}</main>
    </div>
  );
}
