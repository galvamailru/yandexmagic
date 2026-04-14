"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  CartesianGrid,
} from "recharts";
import { Shell } from "@/components/shell";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { apiFetch, getToken } from "@/lib/api";
import { statusLabel } from "@/lib/recommendation-format";
import { toast } from "sonner";

type Summary = { campaigns_count: number; total_spend_rub: string; avg_cpc_rub: string | null };
type Rec = { id: string; title: string; body: string; status: string; created_at: string | null };
type AutomationKpis = {
  recommendations_total: number;
  recommendations_pending: number;
  recommendations_applied: number;
  recommendations_apply_rate_pct: number;
  actions_7d: number;
  campaigns_total: number;
  campaigns_autopilot: number;
  autopilot_share_pct: number;
};

export default function DashboardPage() {
  const router = useRouter();
  const [me, setMe] = useState<{ is_platform_admin: boolean } | null>(null);
  const [sum, setSum] = useState<Summary | null>(null);
  const [kpis, setKpis] = useState<AutomationKpis | null>(null);
  const [chart, setChart] = useState<{ date: string; cost_rub: number }[]>([]);
  const [recs, setRecs] = useState<Rec[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    (async () => {
      try {
        const u = await apiFetch<{ is_platform_admin: boolean }>("/api/me");
        setMe(u);
        const s = await apiFetch<Summary>("/api/dashboard/summary");
        setSum(s);
        const c = await apiFetch<{ date: string; cost_rub: number }[]>("/api/dashboard/spend-chart?days=14");
        setChart(c);
        const a = await apiFetch<AutomationKpis>("/api/dashboard/automation-kpis");
        setKpis(a);
        const r = await apiFetch<Rec[]>("/api/dashboard/recommendations?limit=10");
        setRecs(r);
      } catch (e) {
        toast.error(String(e));
      } finally {
        setLoading(false);
      }
    })();
  }, [router]);

  if (loading || !me) {
    return (
      <Shell isAdmin={false}>
        <div className="space-y-4">
          <Skeleton className="h-10 w-64" />
          <div className="grid md:grid-cols-3 gap-4">
            <Skeleton className="h-28" />
            <Skeleton className="h-28" />
            <Skeleton className="h-28" />
          </div>
        </div>
      </Shell>
    );
  }

  return (
    <Shell isAdmin={me.is_platform_admin}>
      <div className="max-w-6xl mx-auto space-y-8">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Дашборд</h1>
          <p className="text-[hsl(var(--muted-foreground))]">Обзор кампаний и AI-рекомендаций</p>
        </div>

        <div className="grid md:grid-cols-3 gap-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium text-[hsl(var(--muted-foreground))]">Кампании</CardTitle>
            </CardHeader>
            <CardContent className="text-3xl font-semibold">{sum?.campaigns_count ?? "—"}</CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium text-[hsl(var(--muted-foreground))]">Расход</CardTitle>
            </CardHeader>
            <CardContent className="text-3xl font-semibold">{sum ? `${Number(sum.total_spend_rub).toFixed(2)} ₽` : "—"}</CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium text-[hsl(var(--muted-foreground))]">Средняя цена клика</CardTitle>
            </CardHeader>
            <CardContent className="text-3xl font-semibold">
              {sum?.avg_cpc_rub ? `${Number(sum.avg_cpc_rub).toFixed(2)} ₽` : "—"}
            </CardContent>
          </Card>
        </div>

        <div className="grid md:grid-cols-4 gap-4">
          <Card>
            <CardHeader><CardTitle className="text-sm font-medium text-[hsl(var(--muted-foreground))]">Применение рекомендаций</CardTitle></CardHeader>
            <CardContent className="text-3xl font-semibold">{kpis ? `${kpis.recommendations_apply_rate_pct}%` : "—"}</CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-sm font-medium text-[hsl(var(--muted-foreground))]">Ожидают обработки</CardTitle></CardHeader>
            <CardContent className="text-3xl font-semibold">{kpis?.recommendations_pending ?? "—"}</CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-sm font-medium text-[hsl(var(--muted-foreground))]">Автодействий за 7 дней</CardTitle></CardHeader>
            <CardContent className="text-3xl font-semibold">{kpis?.actions_7d ?? "—"}</CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-sm font-medium text-[hsl(var(--muted-foreground))]">Доля автопилота</CardTitle></CardHeader>
            <CardContent className="text-3xl font-semibold">{kpis ? `${kpis.autopilot_share_pct}%` : "—"}</CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Расход по дням</CardTitle>
          </CardHeader>
          <CardContent className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chart}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip />
                <Line type="monotone" dataKey="cost_rub" stroke="hsl(221, 83%, 53%)" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between gap-3">
              <CardTitle>Последние рекомендации AI</CardTitle>
              <Button asChild variant="outline" size="sm">
                <Link href="/recommendations">Открыть аналитику</Link>
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {recs.length === 0 && <p className="text-sm text-[hsl(var(--muted-foreground))]">Пока пусто</p>}
            {recs.map((r) => (
              <div key={r.id} className="border border-[hsl(var(--border))] rounded-lg p-3">
                <div className="font-medium">{r.title}</div>
                <div className="text-sm text-[hsl(var(--muted-foreground))]">{r.body}</div>
                <div className="text-xs mt-1 text-[hsl(var(--muted-foreground))]">
                  {statusLabel(r.status)} {r.created_at ? `• ${new Date(r.created_at).toLocaleString("ru-RU")}` : ""}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </Shell>
  );
}
