"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Eye, Lightbulb, Bot, Filter } from "lucide-react";
import { toast } from "sonner";
import { Shell } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch, getToken } from "@/lib/api";
import { cn } from "@/lib/utils";

type Camp = {
  id: string;
  yandex_campaign_id: number;
  name: string;
  state: string;
  mode: string;
};

const modes = [
  { id: "monitoring", label: "Мониторинг", icon: Eye },
  { id: "advisor", label: "Советник", icon: Lightbulb },
  { id: "autopilot", label: "Автопилот", icon: Bot },
];

export default function CampaignsPage() {
  const router = useRouter();
  const [me, setMe] = useState<{ is_platform_admin: boolean; autopilot_risk_accepted_at: string | null } | null>(
    null
  );
  const [rows, setRows] = useState<Camp[]>([]);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    const list = await apiFetch<Camp[]>("/api/campaigns");
    setRows(list);
  }

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    (async () => {
      try {
        const u = await apiFetch<{ is_platform_admin: boolean; autopilot_risk_accepted_at: string | null }>("/api/me");
        setMe(u);
        await load();
      } catch (e) {
        toast.error(String(e));
      } finally {
        setLoading(false);
      }
    })();
  }, [router]);

  const filtered = useMemo(
    () => rows.filter((c) => c.name.toLowerCase().includes(q.toLowerCase())),
    [rows, q]
  );

  async function setMode(id: string, mode: string) {
    try {
      if (mode === "autopilot" && !me?.autopilot_risk_accepted_at) {
        toast.error("Сначала примите риски автопилота в разделе мастера или /me");
        return;
      }
      await apiFetch(`/api/campaigns/${id}/mode`, { method: "PATCH", body: JSON.stringify({ mode }) });
      toast.success("Режим обновлён");
      await load();
    } catch (e) {
      toast.error(String(e));
    }
  }

  async function genRec(id: string) {
    try {
      await apiFetch(`/api/campaigns/${id}/recommendations/generate`, { method: "POST" });
      toast.success("Рекомендации сгенерированы");
    } catch (e) {
      toast.error(String(e));
    }
  }

  async function applyAll(id: string) {
    try {
      await apiFetch(`/api/campaigns/${id}/recommendations/apply-all`, { method: "POST" });
      toast.success("Рекомендации применены");
    } catch (e) {
      toast.error(String(e));
    }
  }

  if (loading || !me) {
    return (
      <Shell isAdmin={false}>
        <Skeleton className="h-10 w-64" />
      </Shell>
    );
  }

  return (
    <Shell isAdmin={me.is_platform_admin}>
      <div className="max-w-6xl mx-auto space-y-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold">Кампании</h1>
            <p className="text-[hsl(var(--muted-foreground))]">Режимы AI и действия</p>
          </div>
          <div className="relative w-72">
            <Filter className="absolute left-3 top-2.5 h-4 w-4 text-[hsl(var(--muted-foreground))]" />
            <Input className="pl-9" placeholder="Фильтр по названию" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Список</CardTitle>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[hsl(var(--muted-foreground))]">
                  <th className="pb-2">Название</th>
                  <th className="pb-2">Состояние</th>
                  <th className="pb-2">Режим</th>
                  <th className="pb-2">Действия</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((c) => (
                  <tr key={c.id} className="border-t border-[hsl(var(--border))]">
                    <td className="py-3 font-medium">{c.name}</td>
                    <td className="py-3">{c.state}</td>
                    <td className="py-3">
                      <div className="flex flex-wrap gap-2">
                        {modes.map((m) => {
                          const Icon = m.icon;
                          const active = c.mode === m.id;
                          return (
                            <button
                              key={m.id}
                              type="button"
                              onClick={() => setMode(c.id, m.id)}
                              className={cn(
                                "inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs",
                                active
                                  ? "border-[hsl(var(--primary))] bg-blue-50 text-[hsl(var(--primary))]"
                                  : "border-[hsl(var(--border))] hover:bg-[hsl(var(--muted))]"
                              )}
                            >
                              <Icon className="h-3.5 w-3.5" />
                              {m.label}
                            </button>
                          );
                        })}
                      </div>
                    </td>
                    <td className="py-3 space-x-2 whitespace-nowrap">
                      <Button size="sm" variant="outline" asChild>
                        <Link href={`/campaigns/${c.id}`}>Открыть</Link>
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => genRec(c.id)}>
                        Рекомендации
                      </Button>
                      <Button size="sm" onClick={() => applyAll(c.id)}>
                        Применить всё
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      </div>
    </Shell>
  );
}
