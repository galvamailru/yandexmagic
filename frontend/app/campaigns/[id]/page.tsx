"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Shell } from "@/components/shell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetch, getToken } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { kindBadgeClass, kindLabel, statusBadgeClass, statusLabel } from "@/lib/recommendation-format";
import { toast } from "sonner";

type Detail = {
  campaign: { id: string; yandex_campaign_id: number; name: string; state: string; mode: string };
  stats: { date: string; cost_rub: number; clicks: number; impressions: number; ctr: number; avg_cpc_rub: number | null }[];
  recommendations: { id: string; title: string; body: string; kind: string; status: string; created_at: string | null }[];
  logs: { id: string; message: string; level: string; created_at: string | null }[];
};

export default function CampaignDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const [isAdmin, setIsAdmin] = useState(false);
  const [data, setData] = useState<Detail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    (async () => {
      try {
        const me = await apiFetch<{ is_platform_admin: boolean }>("/api/me");
        setIsAdmin(me.is_platform_admin);
        const d = await apiFetch<Detail>(`/api/campaigns/${params.id}`);
        setData(d);
      } catch (e) {
        toast.error(String(e));
      } finally {
        setLoading(false);
      }
    })();
  }, [params.id, router]);

  const totals = useMemo(() => {
    if (!data) return { spend: 0, clicks: 0, impr: 0 };
    return data.stats.reduce(
      (acc, s) => ({ spend: acc.spend + s.cost_rub, clicks: acc.clicks + s.clicks, impr: acc.impr + s.impressions }),
      { spend: 0, clicks: 0, impr: 0 }
    );
  }, [data]);

  return (
    <Shell isAdmin={isAdmin}>
      <div className="max-w-6xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-semibold">{data?.campaign.name || "Кампания"}</h1>
            <p className="text-[hsl(var(--muted-foreground))]">Детали и параметры кампании</p>
          </div>
          <Button variant="outline" asChild>
            <Link href="/campaigns">Назад к списку</Link>
          </Button>
        </div>

        {!loading && data && (
          <>
            <div className="grid md:grid-cols-4 gap-4">
              <Card><CardContent className="p-4"><div className="text-xs text-[hsl(var(--muted-foreground))]">Yandex ID</div><div className="font-semibold">{data.campaign.yandex_campaign_id}</div></CardContent></Card>
              <Card><CardContent className="p-4"><div className="text-xs text-[hsl(var(--muted-foreground))]">Режим</div><div className="font-semibold">{data.campaign.mode}</div></CardContent></Card>
              <Card><CardContent className="p-4"><div className="text-xs text-[hsl(var(--muted-foreground))]">Расход (30 дн)</div><div className="font-semibold">{totals.spend.toFixed(2)} ₽</div></CardContent></Card>
              <Card><CardContent className="p-4"><div className="text-xs text-[hsl(var(--muted-foreground))]">Клики / показы</div><div className="font-semibold">{totals.clicks} / {totals.impr}</div></CardContent></Card>
            </div>

            <Card>
              <CardHeader><CardTitle>Последние рекомендации</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                {data.recommendations.map((r) => (
                  <div key={r.id} className="rounded border p-3">
                    <div className="font-medium">{r.title}</div>
                    <div className="text-sm text-[hsl(var(--muted-foreground))]">{r.body}</div>
                    <div className="mt-2 flex items-center gap-2">
                      <span className={kindBadgeClass(r.kind)}>{kindLabel(r.kind)}</span>
                      <span className={statusBadgeClass(r.status)}>{statusLabel(r.status)}</span>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle>Логи агента</CardTitle></CardHeader>
              <CardContent className="space-y-2 text-sm">
                {data.logs.map((l) => (
                  <div key={l.id} className="border-b pb-2">
                    <div className="text-xs text-[hsl(var(--muted-foreground))]">{l.created_at ? new Date(l.created_at).toLocaleString("ru-RU") : ""}</div>
                    <div>[{l.level}] {l.message}</div>
                  </div>
                ))}
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </Shell>
  );
}
