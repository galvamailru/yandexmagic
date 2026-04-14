"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Shell } from "@/components/shell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetch, getToken } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { kindBadgeClass, kindLabel, recommendationCardClass, statusBadgeClass, statusLabel } from "@/lib/recommendation-format";
import { toast } from "sonner";

type Detail = {
  campaign: { id: string; yandex_campaign_id: number; name: string; state: string; mode: string };
  stats: { date: string; cost_rub: number; clicks: number; impressions: number; ctr: number; avg_cpc_rub: number | null }[];
  recommendations: { id: string; title: string; body: string; kind: string; status: string; created_at: string | null }[];
  logs: { id: string; message: string; level: string; created_at: string | null }[];
};
type AgentSettings = {
  ctr_low_threshold: number;
  ctr_high_threshold: number;
  cost_threshold_rub: number;
  bid_up_factor: number;
  autopilot_dry_run: boolean;
  max_changes_per_cycle: number;
};
type PreviewAction = { keyword_id: number; keyword: string; action: string; new_bid_rub?: number };
type Paged<T> = { items: T[]; total: number; page: number; limit: number };
type HistoryItem = {
  id: string;
  campaign_id: string | null;
  action_type: string;
  payload_before: Record<string, unknown>;
  payload_after: Record<string, unknown>;
  correlation_id: string | null;
  created_at: string | null;
};
type KeywordRow = { id: number; keyword: string; state: string; bid_rub: number; cost_rub: number; ctr: number };
type AdRow = { id: number; title: string; state: string; cost_rub: number; clicks: number; impressions: number };

export default function CampaignDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const [isAdmin, setIsAdmin] = useState(false);
  const [data, setData] = useState<Detail | null>(null);
  const [settings, setSettings] = useState<AgentSettings | null>(null);
  const [preview, setPreview] = useState<PreviewAction[]>([]);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [recommendations, setRecommendations] = useState<Detail["recommendations"]>([]);
  const [logs, setLogs] = useState<Detail["logs"]>([]);
  const [loading, setLoading] = useState(true);
  const [savingSettings, setSavingSettings] = useState(false);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [undoing, setUndoing] = useState(false);
  const [tab, setTab] = useState<"settings" | "preview" | "history" | "recommendations" | "logs" | "keywords" | "ads">("settings");
  const [previewPage, setPreviewPage] = useState(1);
  const [historyPage, setHistoryPage] = useState(1);
  const [recPage, setRecPage] = useState(1);
  const [logPage, setLogPage] = useState(1);
  const [keywordPage, setKeywordPage] = useState(1);
  const [adPage, setAdPage] = useState(1);
  const pageSize = 6;
  const [historyTotal, setHistoryTotal] = useState(0);
  const [recTotal, setRecTotal] = useState(0);
  const [logTotal, setLogTotal] = useState(0);
  const [keywords, setKeywords] = useState<KeywordRow[]>([]);
  const [keywordTotal, setKeywordTotal] = useState(0);
  const [ads, setAds] = useState<AdRow[]>([]);
  const [adTotal, setAdTotal] = useState(0);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    (async () => {
      try {
        const me = await apiFetch<{ is_platform_admin: boolean }>("/api/me");
        setIsAdmin(me.is_platform_admin);
        const [d, s] = await Promise.all([
          apiFetch<Detail>(`/api/campaigns/${params.id}`),
          apiFetch<AgentSettings>("/api/campaigns/agent-settings"),
        ]);
        const [h, r, l, k, a] = await Promise.all([
          apiFetch<Paged<HistoryItem>>(`/api/campaigns/${params.id}/action-history?page=${historyPage}&limit=${pageSize}`),
          apiFetch<Paged<Detail["recommendations"][number]>>(
            `/api/campaigns/${params.id}/recommendations?page=${recPage}&limit=${pageSize}`
          ),
          apiFetch<Paged<Detail["logs"][number]>>(`/api/campaigns/${params.id}/logs?page=${logPage}&limit=${pageSize}`),
          apiFetch<Paged<KeywordRow>>(`/api/campaigns/${params.id}/keywords?page=${keywordPage}&limit=${pageSize}`),
          apiFetch<Paged<AdRow>>(`/api/campaigns/${params.id}/ads?page=${adPage}&limit=${pageSize}`),
        ]);
        setData(d);
        setSettings(s);
        setHistory(h.items);
        setHistoryTotal(h.total);
        setRecommendations(r.items);
        setRecTotal(r.total);
        setLogs(l.items);
        setLogTotal(l.total);
        setKeywords(k.items);
        setKeywordTotal(k.total);
        setAds(a.items);
        setAdTotal(a.total);
      } catch (e) {
        toast.error(String(e));
      } finally {
        setLoading(false);
      }
    })();
  }, [params.id, router, historyPage, recPage, logPage, keywordPage, adPage]);

  async function setCampaignState(state: "ON" | "SUSPENDED") {
    try {
      const updated = await apiFetch<Detail["campaign"]>(`/api/campaigns/${params.id}/state`, {
        method: "PATCH",
        body: JSON.stringify({ state }),
      });
      setData((prev) => (prev ? { ...prev, campaign: updated } : prev));
      toast.success(state === "ON" ? "Кампания возобновлена" : "Кампания приостановлена");
    } catch (e) {
      toast.error(String(e));
    }
  }

  const totals = useMemo(() => {
    if (!data) return { spend: 0, clicks: 0, impr: 0 };
    return data.stats.reduce(
      (acc, s) => ({ spend: acc.spend + s.cost_rub, clicks: acc.clicks + s.clicks, impr: acc.impr + s.impressions }),
      { spend: 0, clicks: 0, impr: 0 }
    );
  }, [data]);

  async function saveAgentSettings() {
    if (!settings) return;
    setSavingSettings(true);
    try {
      const updated = await apiFetch<AgentSettings>("/api/campaigns/agent-settings", {
        method: "PUT",
        body: JSON.stringify(settings),
      });
      setSettings(updated);
      toast.success("Настройки агента сохранены");
    } catch (e) {
      toast.error(String(e));
    } finally {
      setSavingSettings(false);
    }
  }

  async function loadPreview() {
    setLoadingPreview(true);
    try {
      const res = await apiFetch<{ preview: PreviewAction[] }>(`/api/campaigns/${params.id}/autopilot-preview`);
      setPreview(res.preview || []);
      toast.success("Preview обновлён");
    } catch (e) {
      toast.error(String(e));
    } finally {
      setLoadingPreview(false);
    }
  }

  async function undoLast() {
    setUndoing(true);
    try {
      await apiFetch(`/api/campaigns/${params.id}/undo-last`, { method: "POST" });
      toast.success("Последнее действие отменено");
      const [d, h] = await Promise.all([
        apiFetch<Detail>(`/api/campaigns/${params.id}`),
        apiFetch<Paged<HistoryItem>>(`/api/campaigns/${params.id}/action-history?page=${historyPage}&limit=${pageSize}`),
      ]);
      setData(d);
      setHistory(h.items);
      setHistoryTotal(h.total);
    } catch (e) {
      toast.error(String(e));
    } finally {
      setUndoing(false);
    }
  }

  function pageCount(total: number) {
    return Math.max(1, Math.ceil(total / pageSize));
  }
  return (
    <Shell isAdmin={isAdmin}>
      <div className="max-w-6xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-semibold">{data?.campaign.name || "Кампания"}</h1>
            <p className="text-[hsl(var(--muted-foreground))]">Детали и параметры кампании</p>
          </div>
          <div className="flex gap-2">
            {data?.campaign.state === "ON" ? (
              <Button variant="outline" onClick={() => setCampaignState("SUSPENDED")}>Пауза</Button>
            ) : (
              <Button variant="outline" onClick={() => setCampaignState("ON")}>Возобновить</Button>
            )}
            <Button variant="outline" asChild>
              <Link href="/campaigns">Назад к списку</Link>
            </Button>
          </div>
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
              <CardHeader><CardTitle>Вкладки кампании</CardTitle></CardHeader>
              <CardContent className="flex flex-wrap gap-2">
                <Button size="sm" variant={tab === "settings" ? "default" : "outline"} onClick={() => setTab("settings")}>Настройки</Button>
                <Button size="sm" variant={tab === "preview" ? "default" : "outline"} onClick={() => setTab("preview")}>Preview</Button>
                <Button size="sm" variant={tab === "keywords" ? "default" : "outline"} onClick={() => setTab("keywords")}>Ключевые слова</Button>
                <Button size="sm" variant={tab === "ads" ? "default" : "outline"} onClick={() => setTab("ads")}>Объявления</Button>
                <Button size="sm" variant={tab === "history" ? "default" : "outline"} onClick={() => setTab("history")}>Аудит</Button>
                <Button size="sm" variant={tab === "recommendations" ? "default" : "outline"} onClick={() => setTab("recommendations")}>Рекомендации</Button>
                <Button size="sm" variant={tab === "logs" ? "default" : "outline"} onClick={() => setTab("logs")}>Логи</Button>
              </CardContent>
            </Card>

            {tab === "settings" && (
            <Card>
              <CardHeader><CardTitle>Настройки агента</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                {settings && (
                  <>
                    <div className="grid md:grid-cols-3 gap-3">
                      <div><div className="text-xs mb-1 text-[hsl(var(--muted-foreground))]">CTR низкий порог</div><Input type="number" step="0.1" value={settings.ctr_low_threshold} onChange={(e) => setSettings({ ...settings, ctr_low_threshold: Number(e.target.value) })} /></div>
                      <div><div className="text-xs mb-1 text-[hsl(var(--muted-foreground))]">CTR высокий порог</div><Input type="number" step="0.1" value={settings.ctr_high_threshold} onChange={(e) => setSettings({ ...settings, ctr_high_threshold: Number(e.target.value) })} /></div>
                      <div><div className="text-xs mb-1 text-[hsl(var(--muted-foreground))]">Порог расхода, ₽</div><Input type="number" step="1" value={settings.cost_threshold_rub} onChange={(e) => setSettings({ ...settings, cost_threshold_rub: Number(e.target.value) })} /></div>
                      <div><div className="text-xs mb-1 text-[hsl(var(--muted-foreground))]">Коэфф. повышения ставки</div><Input type="number" step="0.01" value={settings.bid_up_factor} onChange={(e) => setSettings({ ...settings, bid_up_factor: Number(e.target.value) })} /></div>
                      <div><div className="text-xs mb-1 text-[hsl(var(--muted-foreground))]">Лимит изменений/цикл</div><Input type="number" step="1" value={settings.max_changes_per_cycle} onChange={(e) => setSettings({ ...settings, max_changes_per_cycle: Number(e.target.value) })} /></div>
                      <div className="flex items-end pb-2">
                        <label className="text-sm flex items-center gap-2">
                          <input type="checkbox" checked={settings.autopilot_dry_run} onChange={(e) => setSettings({ ...settings, autopilot_dry_run: e.target.checked })} />
                          Dry-run автопилота
                        </label>
                      </div>
                    </div>
                    <Button onClick={saveAgentSettings} disabled={savingSettings}>
                      {savingSettings ? "Сохраняем..." : "Сохранить настройки"}
                    </Button>
                  </>
                )}
              </CardContent>
            </Card>
            )}

            {tab === "keywords" && (
            <Card>
              <CardHeader><CardTitle>Ключевые слова и стоимость</CardTitle></CardHeader>
              <CardContent className="space-y-2 text-sm overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-[hsl(var(--muted-foreground))]">
                      <th>Фраза</th><th>Состояние</th><th>Ставка</th><th>Расход</th><th>CTR</th>
                    </tr>
                  </thead>
                  <tbody>
                    {keywords.map((k) => (
                      <tr key={k.id} className="border-t">
                        <td>{k.keyword}</td>
                        <td>{k.state}</td>
                        <td>{k.bid_rub.toFixed(2)} ₽</td>
                        <td>{k.cost_rub.toFixed(2)} ₽</td>
                        <td>{k.ctr.toFixed(2)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="flex items-center justify-between pt-2">
                  <div className="text-xs text-[hsl(var(--muted-foreground))]">Страница {keywordPage} / {pageCount(keywordTotal)}</div>
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" disabled={keywordPage <= 1} onClick={() => setKeywordPage((p) => p - 1)}>Назад</Button>
                    <Button size="sm" variant="outline" disabled={keywordPage >= pageCount(keywordTotal)} onClick={() => setKeywordPage((p) => p + 1)}>Далее</Button>
                  </div>
                </div>
              </CardContent>
            </Card>
            )}

            {tab === "ads" && (
            <Card>
              <CardHeader><CardTitle>Объявления и стоимость</CardTitle></CardHeader>
              <CardContent className="space-y-2 text-sm overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-[hsl(var(--muted-foreground))]">
                      <th>Объявление</th><th>Состояние</th><th>Расход</th><th>Клики</th><th>Показы</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ads.map((a) => (
                      <tr key={a.id} className="border-t">
                        <td>{a.title}</td>
                        <td>{a.state}</td>
                        <td>{a.cost_rub.toFixed(2)} ₽</td>
                        <td>{a.clicks}</td>
                        <td>{a.impressions}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="flex items-center justify-between pt-2">
                  <div className="text-xs text-[hsl(var(--muted-foreground))]">Страница {adPage} / {pageCount(adTotal)}</div>
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" disabled={adPage <= 1} onClick={() => setAdPage((p) => p - 1)}>Назад</Button>
                    <Button size="sm" variant="outline" disabled={adPage >= pageCount(adTotal)} onClick={() => setAdPage((p) => p + 1)}>Далее</Button>
                  </div>
                </div>
              </CardContent>
            </Card>
            )}

            {tab === "preview" && (
            <Card>
              <CardHeader><CardTitle>Preview автопилота</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <div className="flex gap-2">
                  <Button variant="outline" onClick={loadPreview} disabled={loadingPreview}>
                    {loadingPreview ? "Обновляем..." : "Обновить preview"}
                  </Button>
                  <Button variant="outline" onClick={undoLast} disabled={undoing}>
                    {undoing ? "Откатываем..." : "Откатить последнее действие"}
                  </Button>
                </div>
                {preview.length === 0 ? (
                  <p className="text-sm text-[hsl(var(--muted-foreground))]">Нет действий по текущим правилам.</p>
                ) : (
                  <div className="space-y-2">
                    {preview.slice((previewPage - 1) * pageSize, previewPage * pageSize).map((p, i) => (
                      <div key={`${p.keyword_id}-${i}`} className="rounded border p-2 text-sm">
                        <span className="font-medium">{p.keyword}</span> → {p.action}
                        {typeof p.new_bid_rub === "number" ? ` (${p.new_bid_rub} ₽)` : ""}
                      </div>
                    ))}
                    <div className="flex items-center justify-between pt-2">
                      <div className="text-xs text-[hsl(var(--muted-foreground))]">Страница {previewPage} / {pageCount(preview.length)}</div>
                      <div className="flex gap-2">
                        <Button size="sm" variant="outline" disabled={previewPage <= 1} onClick={() => setPreviewPage((p) => p - 1)}>Назад</Button>
                        <Button size="sm" variant="outline" disabled={previewPage >= pageCount(preview.length)} onClick={() => setPreviewPage((p) => p + 1)}>Далее</Button>
                      </div>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
            )}

            {tab === "history" && (
            <Card>
              <CardHeader><CardTitle>История действий (audit)</CardTitle></CardHeader>
              <CardContent className="space-y-2 text-sm">
                {history.map((h) => (
                  <div key={h.id} className="border-b pb-2">
                    <div className="text-xs text-[hsl(var(--muted-foreground))]">
                      {h.created_at ? new Date(h.created_at).toLocaleString("ru-RU") : ""} • {h.action_type}
                    </div>
                    <div>До: {JSON.stringify(h.payload_before)}</div>
                    <div>После: {JSON.stringify(h.payload_after)}</div>
                    {h.correlation_id && (
                      <div className="text-xs text-[hsl(var(--muted-foreground))]">corr: {h.correlation_id}</div>
                    )}
                  </div>
                ))}
                <div className="flex items-center justify-between pt-2">
                  <div className="text-xs text-[hsl(var(--muted-foreground))]">Страница {historyPage} / {pageCount(historyTotal)}</div>
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" disabled={historyPage <= 1} onClick={() => setHistoryPage((p) => p - 1)}>Назад</Button>
                    <Button size="sm" variant="outline" disabled={historyPage >= pageCount(historyTotal)} onClick={() => setHistoryPage((p) => p + 1)}>Далее</Button>
                  </div>
                </div>
              </CardContent>
            </Card>
            )}

            {tab === "recommendations" && (
            <Card>
              <CardHeader><CardTitle>Последние рекомендации</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                {recommendations.map((r) => (
                  <div key={r.id} className={recommendationCardClass(r.kind)}>
                    <div className="font-medium">{r.title}</div>
                    <div className="text-sm text-[hsl(var(--muted-foreground))]">{r.body}</div>
                    <div className="mt-2 flex items-center gap-2">
                      <span className={kindBadgeClass(r.kind)}>{kindLabel(r.kind)}</span>
                      <span className={statusBadgeClass(r.status)}>{statusLabel(r.status)}</span>
                    </div>
                  </div>
                ))}
                <div className="flex items-center justify-between pt-2">
                  <div className="text-xs text-[hsl(var(--muted-foreground))]">Страница {recPage} / {pageCount(recTotal)}</div>
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" disabled={recPage <= 1} onClick={() => setRecPage((p) => p - 1)}>Назад</Button>
                    <Button size="sm" variant="outline" disabled={recPage >= pageCount(recTotal)} onClick={() => setRecPage((p) => p + 1)}>Далее</Button>
                  </div>
                </div>
              </CardContent>
            </Card>
            )}

            {tab === "logs" && (
            <Card>
              <CardHeader><CardTitle>Логи агента</CardTitle></CardHeader>
              <CardContent className="space-y-2 text-sm">
                {logs.map((l) => (
                  <div key={l.id} className="border-b pb-2">
                    <div className="text-xs text-[hsl(var(--muted-foreground))]">{l.created_at ? new Date(l.created_at).toLocaleString("ru-RU") : ""}</div>
                    <div>[{l.level}] {l.message}</div>
                  </div>
                ))}
                <div className="flex items-center justify-between pt-2">
                  <div className="text-xs text-[hsl(var(--muted-foreground))]">Страница {logPage} / {pageCount(logTotal)}</div>
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" disabled={logPage <= 1} onClick={() => setLogPage((p) => p - 1)}>Назад</Button>
                    <Button size="sm" variant="outline" disabled={logPage >= pageCount(logTotal)} onClick={() => setLogPage((p) => p + 1)}>Далее</Button>
                  </div>
                </div>
              </CardContent>
            </Card>
            )}
          </>
        )}
      </div>
    </Shell>
  );
}
