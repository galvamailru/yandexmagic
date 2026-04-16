"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { LayoutDashboard, Megaphone, Sparkles, Shield, LogOut, ListFilter, BookOpen, UserCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";

const nav = [
  { href: "/dashboard", label: "Дашборд", icon: LayoutDashboard },
  { href: "/campaigns", label: "Кампании", icon: Megaphone },
  { href: "/recommendations", label: "Рекомендации", icon: ListFilter },
  { href: "/profile", label: "Профиль", icon: UserCircle2 },
  { href: "/wizard", label: "Новая кампания", icon: Sparkles },
  { href: "/help", label: "Wiki / Help", icon: BookOpen },
];

export function Shell({
  children,
  isAdmin,
}: {
  children: React.ReactNode;
  isAdmin?: boolean;
}) {
  const path = usePathname();
  const router = useRouter();
  const [sandboxOn, setSandboxOn] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const meta = await apiFetch<{ yandex_sandbox: boolean }>("/api/meta");
        setSandboxOn(Boolean(meta.yandex_sandbox));
      } catch {
        // ignore
      }
    })();
  }, []);

  function logout() {
    localStorage.removeItem("ym_token");
    router.push("/login");
  }

  return (
    <div className="min-h-screen flex">
      <aside className="w-64 border-r border-[hsl(var(--border))] bg-white p-4 flex flex-col gap-6">
        <div>
          <div className="text-xs uppercase tracking-wider text-[hsl(var(--muted-foreground))]">YandexMagic</div>
          <div className="text-lg font-semibold flex items-center gap-2">
            AI для Директа
            {sandboxOn && (
              <span className="text-xs font-medium rounded-full bg-amber-100 text-amber-800 px-2 py-0.5">
                Sandbox включён
              </span>
            )}
          </div>
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
        <div className="mt-auto">
          <Button variant="outline" className="w-full justify-start gap-2" onClick={logout}>
            <LogOut className="h-4 w-4" />
            Выйти
          </Button>
        </div>
      </aside>
      <main className="flex-1 p-8 bg-gradient-to-br from-slate-50 to-white">{children}</main>
    </div>
  );
}
