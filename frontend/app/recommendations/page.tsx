"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Shell } from "@/components/shell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { apiFetch, getToken } from "@/lib/api";
import { kindBadgeClass, kindLabel, statusBadgeClass, statusLabel } from "@/lib/recommendation-format";
import { toast } from "sonner";

type Campaign = { id: string; name: string };
type Rec = {
  id: string;
  campaign_id: string | null;
  campaign_name: string | null;
  kind: string;
  title: string;
  body: string;
  status: string;
  created_at: string | null;
};

type ParsedRec = {
  kind?: string;
  title?: string;
  body?: string;
  payload?: Record<string, unknown>;
};

function extractStructuredRecommendations(rawBody: string): ParsedRec[] {
  try {
    const parsed = JSON.parse(rawBody);
    if (Array.isArray(parsed)) {
      return parsed as ParsedRec[];
    }
    if (parsed && Array.isArray(parsed.recommendations)) {
      return parsed.recommendations as ParsedRec[];
    }
  } catch {
    return [];
  }
  return [];
}

export default function RecommendationsPage() {
  const router = useRouter();
  const [isAdmin, setIsAdmin] = useState(false);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [rows, setRows] = useState<Rec[]>([]);
  const [loading, setLoading] = useState(true);

  const [campaignId, setCampaignId] = useState("");
  const [status, setStatus] = useState("");
  const [kind, setKind] = useState("");
  const [search, setSearch] = useState("");

  async function loadData() {
    const params = new URLSearchParams();
    if (campaignId) params.set("campaign_id", campaignId);
    if (status) params.set("status", status);
    if (kind) params.set("kind", kind);
    if (search.trim()) params.set("search", search.trim());
    params.set("limit", "200");
    const [camps, recs] = await Promise.all([
      apiFetch<Campaign[]>("/api/dashboard/campaigns-options"),
      apiFetch<Rec[]>(`/api/dashboard/recommendations-analytics?${params.toString()}`),
    ]);
    setCampaigns(camps);
    setRows(recs);
  }

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    (async () => {
      try {
        const me = await apiFetch<{ is_platform_admin: boolean }>("/api/me");
        setIsAdmin(me.is_platform_admin);
        await loadData();
      } catch (e) {
        toast.error(String(e));
      } finally {
        setLoading(false);
      }
    })();
  }, [router]);

  const stats = useMemo(() => {
    const total = rows.length;
    const pending = rows.filter((x) => x.status === "pending").length;
    const applied = rows.filter((x) => x.status === "applied").length;
    return { total, pending, applied };
  }, [rows]);

  async function applyFilters() {
    setLoading(true);
    try {
      await loadData();
    } catch (e) {
      toast.error(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Shell isAdmin={isAdmin}>
      <div className="max-w-6xl mx-auto space-y-6">
        <div>
          <h1 className="text-3xl font-semibold">Рекомендации AI</h1>
          <p className="text-[hsl(var(--muted-foreground))]">
            Формализованная аналитика: что агент увидел и какие действия предлагает.
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-4">
          <Card><CardContent className="p-4"><div className="text-sm text-[hsl(var(--muted-foreground))]">Всего</div><div className="text-2xl font-semibold">{stats.total}</div></CardContent></Card>
          <Card><CardContent className="p-4"><div className="text-sm text-[hsl(var(--muted-foreground))]">Ожидают применения</div><div className="text-2xl font-semibold">{stats.pending}</div></CardContent></Card>
          <Card><CardContent className="p-4"><div className="text-sm text-[hsl(var(--muted-foreground))]">Применено</div><div className="text-2xl font-semibold">{stats.applied}</div></CardContent></Card>
        </div>

        <Card>
          <CardHeader><CardTitle>Фильтры</CardTitle></CardHeader>
          <CardContent className="grid md:grid-cols-5 gap-3">
            <select className="h-10 rounded-md border px-3" value={campaignId} onChange={(e) => setCampaignId(e.target.value)}>
              <option value="">Все компании</option>
              {campaigns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <select className="h-10 rounded-md border px-3" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">Все статусы</option>
              <option value="pending">Ожидает применения</option>
              <option value="applied">Применено</option>
            </select>
            <select className="h-10 rounded-md border px-3" value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="">Все типы</option>
              <option value="keyword">Ключевая фраза</option>
              <option value="general">Общий вывод</option>
              <option value="warning">Риск</option>
              <option value="success">Эффективно</option>
            </select>
            <Input placeholder="Поиск по выводу/рекомендации" value={search} onChange={(e) => setSearch(e.target.value)} />
            <Button onClick={applyFilters} disabled={loading}>{loading ? "Обновляем..." : "Применить"}</Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Список рекомендаций</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {!loading && rows.length === 0 && (
              <p className="text-sm text-[hsl(var(--muted-foreground))]">По текущим фильтрам данных нет.</p>
            )}
            {rows.map((r) => (
              <div key={r.id} className="rounded-lg border p-4 bg-white space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-semibold">{r.title}</div>
                  <div className="text-xs text-[hsl(var(--muted-foreground))]">
                    {r.created_at ? new Date(r.created_at).toLocaleString("ru-RU") : "—"}
                  </div>
                </div>
                <div className="text-sm">
                  <span className="font-medium">Компания:</span> {r.campaign_name || "Не указана"}
                </div>
                <div className="flex items-center gap-2">
                  <span className={kindBadgeClass(r.kind)}>{kindLabel(r.kind)}</span>
                  <span className={statusBadgeClass(r.status)}>{statusLabel(r.status)}</span>
                </div>
                <div className="text-sm leading-6">
                  <span className="font-medium">Вывод агента и рекомендация:</span>
                  {extractStructuredRecommendations(r.body).length > 0 ? (
                    <div className="mt-2 space-y-2">
                      {extractStructuredRecommendations(r.body).map((sr, idx) => (
                        <div key={idx} className="rounded-md border bg-slate-50 p-3">
                          <div className="font-medium">{sr.title || "Рекомендация"}</div>
                          <div className="mt-1">
                            <span className={kindBadgeClass(sr.kind || "general")}>{kindLabel(sr.kind || "general")}</span>
                          </div>
                          <div className="mt-1 text-sm">{sr.body || ""}</div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <span> {r.body}</span>
                  )}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </Shell>
  );
}
