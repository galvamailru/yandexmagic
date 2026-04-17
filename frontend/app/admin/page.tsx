"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Shell } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch, getToken, setToken } from "@/lib/api";
import { jobStatusBadgeClass, logLevelBadgeClass, tenantBlockedBadgeClass } from "@/lib/status-badges";

type Tenant = { id: string; name: string; schema_name: string; is_blocked: boolean };
type JobRun = { id: string; name: string; status: string; started_at: string | null; duration_ms: number | null; details: Record<string, unknown> };
type DomainPrompt = { domain: string; prompt: string };
type DomainSetting = {
  domain: string;
  enabled: boolean;
  max_changes_per_run: number;
  hard_weekly_limit_rub: number;
  schedule_hint: string;
};
type Paged<T> = { items: T[]; total: number; page: number; limit: number };

const DOMAIN_META: Record<string, { title: string; role: string; io: string[] }> = {
  keyword_hygiene: {
    title: "Чистка фраз и минус-слов",
    role: "Роль: фильтрует нецелевой спрос и снижает мусорный расход.",
    io: [
      "Вход: Keywords + Reports + Wordstat",
      "Выход: suspend/resume keyword, add_negative_keywords_campaign",
    ],
  },
  bid_optimization: {
    title: "Оптимизация ставок",
    role: "Роль: повышает/снижает ставки для баланса трафика и CPA/ROMI.",
    io: [
      "Вход: Bid + CTR/Cost/Clicks/Impressions",
      "Выход: set_bid",
    ],
  },
  budget_guard: {
    title: "Контроль бюджета",
    role: "Роль: защищает от перерасхода и аварийных потерь.",
    io: [
      "Вход: дневной/недельный расход, лимиты домена",
      "Выход: suspend_campaign, set_campaign_daily_budget",
    ],
  },
  ad_rotation: {
    title: "Ротация объявлений",
    role: "Роль: отключает слабые креативы и возвращает эффективные.",
    io: [
      "Вход: Ads + метрики объявлений",
      "Выход: suspend_ad, resume_ad",
    ],
  },
  retargeting_tuning: {
    title: "Тюнинг ретаргетинга",
    role: "Роль: корректирует ставки по аудиториям/сегментам.",
    io: [
      "Вход: AudienceTargets + BidModifiers + RetargetingLists",
      "Выход: update_audience_bid_modifier",
    ],
  },
  anomaly_watchdog: {
    title: "Контроль аномалий",
    role: "Роль: детектирует аварийные всплески и защищает кампании.",
    io: [
      "Вход: последние stats + changes_check (watermark)",
      "Выход: suspend_campaign",
    ],
  },
};

export default function AdminPage() {
  const router = useRouter();
  const [rows, setRows] = useState<Tenant[]>([]);
  const [logs, setLogs] = useState<{ message: string; level: string; created_at: string | null }[]>([]);
  const [runs, setRuns] = useState<JobRun[]>([]);
  const [domainPrompts, setDomainPrompts] = useState<DomainPrompt[]>([]);
  const [domainSettings, setDomainSettings] = useState<DomainSetting[]>([]);
  const [savingDomain, setSavingDomain] = useState<string>("");
  const [roleForm, setRoleForm] = useState({ tenantId: "", userId: "", role: "manager" });
  const [savingRole, setSavingRole] = useState(false);
  const [tab, setTab] = useState<"tenants" | "jobs" | "logs" | "prompt">("tenants");
  const [tenantPage, setTenantPage] = useState(1);
  const [runPage, setRunPage] = useState(1);
  const [logPage, setLogPage] = useState(1);
  const pageSize = 8;
  const [tenantTotal, setTenantTotal] = useState(0);
  const [runTotal, setRunTotal] = useState(0);
  const [logTotal, setLogTotal] = useState(0);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    (async () => {
      try {
        const u = await apiFetch<{ is_platform_admin: boolean }>("/api/me");
        if (!u.is_platform_admin) {
          router.replace("/dashboard");
          return;
        }
        const t = await apiFetch<Paged<Tenant>>(`/api/admin/tenants?page=${tenantPage}&limit=${pageSize}`);
        setRows(t.items);
        setTenantTotal(t.total);
        const l = await apiFetch<Paged<{ message: string; level: string; created_at: string | null }>>(
          `/api/admin/agent-logs?page=${logPage}&limit=${pageSize}`
        );
        setLogs(l.items);
        setLogTotal(l.total);
        const jr = await apiFetch<Paged<JobRun>>(`/api/admin/job-runs?page=${runPage}&limit=${pageSize}`);
        setRuns(jr.items);
        setRunTotal(jr.total);
        const dp = await apiFetch<{ items: DomainPrompt[] }>("/api/admin/domain-prompts");
        setDomainPrompts(dp.items || []);
        const ds = await apiFetch<DomainSetting[]>("/api/campaigns/domain-settings");
        setDomainSettings(ds || []);
      } catch (e) {
        toast.error(String(e));
      }
    })();
  }, [router, tenantPage, runPage, logPage]);

  async function enter(id: string) {
    const tok = await apiFetch<{ access_token: string }>(`/api/admin/switch-tenant?tenant_id=${id}`, { method: "POST" });
    setToken(tok.access_token);
    toast.success("Контекст переключён");
    router.push("/dashboard");
  }

  async function block(id: string, blocked: boolean) {
    await apiFetch(`/api/admin/tenants/${id}/block?blocked=${blocked}`, { method: "POST" });
    toast.success(blocked ? "Тенант заблокирован" : "Тенант разблокирован");
    const t = await apiFetch<Paged<Tenant>>(`/api/admin/tenants?page=${tenantPage}&limit=${pageSize}`);
    setRows(t.items);
    setTenantTotal(t.total);
  }

  async function saveDomainPrompt(domain: string, promptText: string) {
    setSavingDomain(domain);
    try {
      await apiFetch(`/api/admin/domain-prompts/${domain}`, {
        method: "PUT",
        body: JSON.stringify({ prompt: promptText }),
      });
      toast.success(`Промпт домена ${domain} сохранён`);
      const dp = await apiFetch<{ items: DomainPrompt[] }>("/api/admin/domain-prompts");
      setDomainPrompts(dp.items || []);
    } catch (e) {
      toast.error(String(e));
    } finally {
      setSavingDomain("");
    }
  }

  async function resetDomainPrompt(domain: string) {
    setSavingDomain(domain);
    try {
      await apiFetch(`/api/admin/domain-prompts/${domain}/reset`, { method: "POST" });
      toast.success(`Промпт домена ${domain} сброшен к шаблону`);
      const dp = await apiFetch<{ items: DomainPrompt[] }>("/api/admin/domain-prompts");
      setDomainPrompts(dp.items || []);
    } catch (e) {
      toast.error(String(e));
    } finally {
      setSavingDomain("");
    }
  }

  async function saveRole() {
    if (!roleForm.tenantId || !roleForm.userId) {
      toast.error("Нужно выбрать tenant и указать user_id");
      return;
    }
    setSavingRole(true);
    try {
      await apiFetch(`/api/admin/tenants/${roleForm.tenantId}/membership-role`, {
        method: "POST",
        body: JSON.stringify({ user_id: roleForm.userId, role: roleForm.role }),
      });
      toast.success("Роль обновлена");
    } catch (e) {
      toast.error(String(e));
    } finally {
      setSavingRole(false);
    }
  }

  function pageCount(total: number) {
    return Math.max(1, Math.ceil(total / pageSize));
  }

  return (
    <Shell isAdmin>
      <div className="max-w-6xl mx-auto space-y-8">
        <div>
          <h1 className="text-3xl font-semibold">Админ-панель</h1>
          <p className="text-[hsl(var(--muted-foreground))]">Тенанты и логи агента</p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Данные платформы</CardTitle>
          </CardHeader>
          <CardContent className="flex gap-2">
            <Button variant={tab === "tenants" ? "default" : "outline"} size="sm" onClick={() => setTab("tenants")}>
              Тенанты
            </Button>
            <Button variant={tab === "jobs" ? "default" : "outline"} size="sm" onClick={() => setTab("jobs")}>
              Запуски задач
            </Button>
            <Button variant={tab === "logs" ? "default" : "outline"} size="sm" onClick={() => setTab("logs")}>
              Логи
            </Button>
            <Button variant={tab === "prompt" ? "default" : "outline"} size="sm" onClick={() => setTab("prompt")}>
              Доменные промпты
            </Button>
          </CardContent>
        </Card>

        {tab === "tenants" && (
        <Card>
          <CardHeader>
            <CardTitle>Тенанты</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {rows.map((t) => (
              <div key={t.id} className="flex items-center justify-between border rounded-lg p-3">
                <div>
                  <div className="font-medium flex items-center gap-2">
                    {t.name}
                    <span className={tenantBlockedBadgeClass(t.is_blocked)}>{t.is_blocked ? "Заблокирован" : "Активен"}</span>
                  </div>
                  <div className="text-xs text-[hsl(var(--muted-foreground))]">{t.schema_name}</div>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => enter(t.id)}>
                    Войти
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => block(t.id, !t.is_blocked)}>
                    {t.is_blocked ? "Разблокировать" : "Блокировать"}
                  </Button>
                </div>
              </div>
            ))}
            <div className="flex items-center justify-between pt-2">
              <div className="text-xs text-[hsl(var(--muted-foreground))]">Страница {tenantPage} / {pageCount(tenantTotal)}</div>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" disabled={tenantPage <= 1} onClick={() => setTenantPage((p) => p - 1)}>Назад</Button>
                <Button size="sm" variant="outline" disabled={tenantPage >= pageCount(tenantTotal)} onClick={() => setTenantPage((p) => p + 1)}>Далее</Button>
              </div>
            </div>
          </CardContent>
        </Card>
        )}

        {tab === "tenants" && (
          <Card>
            <CardHeader>
              <CardTitle>Роли</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid md:grid-cols-4 gap-2">
                <select
                  className="h-10 rounded-md border px-3"
                  value={roleForm.tenantId}
                  onChange={(e) => setRoleForm({ ...roleForm, tenantId: e.target.value })}
                >
                  <option value="">Tenant</option>
                  {rows.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
                <Input
                  value={roleForm.userId}
                  onChange={(e) => setRoleForm({ ...roleForm, userId: e.target.value })}
                  placeholder="user_id (UUID)"
                />
                <select
                  className="h-10 rounded-md border px-3"
                  value={roleForm.role}
                  onChange={(e) => setRoleForm({ ...roleForm, role: e.target.value })}
                >
                  <option value="owner">owner</option>
                  <option value="manager">manager</option>
                  <option value="viewer">viewer</option>
                </select>
                <Button onClick={saveRole} disabled={savingRole}>
                  {savingRole ? "Сохраняем..." : "Назначить роль"}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {tab === "prompt" && (
          <Card>
            <CardHeader>
              <CardTitle>Промпты AI-агента</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="text-sm font-medium">Расписание и лимиты доменов</div>
              <div className="overflow-x-auto rounded-lg border border-[hsl(var(--border))]">
                <table className="w-full text-sm">
                  <thead className="bg-[hsl(var(--muted))]">
                    <tr className="text-left">
                      <th className="p-2">Домен</th>
                      <th className="p-2">Включен</th>
                      <th className="p-2">Расписание</th>
                      <th className="p-2">Лимит изменений/запуск</th>
                      <th className="p-2">Недельный лимит (RUB)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {domainSettings.map((s) => (
                      <tr key={s.domain} className="border-t border-[hsl(var(--border))]">
                        <td className="p-2 font-mono text-xs">{s.domain}</td>
                        <td className="p-2">{s.enabled ? "Да" : "Нет"}</td>
                        <td className="p-2">{s.schedule_hint || "—"}</td>
                        <td className="p-2">{s.max_changes_per_run}</td>
                        <td className="p-2">{s.hard_weekly_limit_rub}</td>
                      </tr>
                    ))}
                    {!domainSettings.length && (
                      <tr>
                        <td colSpan={5} className="p-3 text-[hsl(var(--muted-foreground))]">
                          Нет данных domain-settings (проверь контекст tenant и backend API).
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              <div className="pt-4 border-t border-[hsl(var(--border))]" />
              <div className="text-sm font-medium">Промпты доменов</div>
              <div className="space-y-4">
                {domainPrompts.map((dp) => (
                  <div key={dp.domain} className="rounded-lg border border-[hsl(var(--border))] p-3 space-y-2">
                    <div className="text-xs uppercase tracking-wide text-[hsl(var(--muted-foreground))]">{dp.domain}</div>
                    <div className="text-sm font-medium">{DOMAIN_META[dp.domain]?.title || dp.domain}</div>
                    <div className="text-xs text-[hsl(var(--muted-foreground))]">{DOMAIN_META[dp.domain]?.role || ""}</div>
                    <ul className="text-xs text-[hsl(var(--muted-foreground))] list-disc pl-5 space-y-1">
                      {(DOMAIN_META[dp.domain]?.io || []).map((line) => (
                        <li key={`${dp.domain}-${line}`}>{line}</li>
                      ))}
                    </ul>
                    <textarea
                      className="w-full min-h-32 rounded-md border border-[hsl(var(--border))] p-3 text-sm"
                      value={dp.prompt}
                      onChange={(e) =>
                        setDomainPrompts((prev) =>
                          prev.map((x) => (x.domain === dp.domain ? { ...x, prompt: e.target.value } : x))
                        )
                      }
                    />
                    <Button onClick={() => saveDomainPrompt(dp.domain, dp.prompt)} disabled={savingDomain === dp.domain}>
                      {savingDomain === dp.domain ? "Сохраняем..." : `Сохранить ${dp.domain}`}
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => resetDomainPrompt(dp.domain)}
                      disabled={savingDomain === dp.domain}
                    >
                      {savingDomain === dp.domain ? "Сбрасываем..." : "Сбросить к шаблону"}
                    </Button>
                  </div>
                ))}
                {!domainPrompts.length && (
                  <div className="text-sm text-[hsl(var(--muted-foreground))]">
                    Доменные промпты не загружены.
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {tab === "jobs" && (
        <Card>
          <CardHeader>
            <CardTitle>Запуски задач</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[hsl(var(--muted-foreground))]">
                  <th>Время</th><th>Job</th><th>Статус</th><th>Длительность</th><th>Details</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id} className="border-t">
                    <td>{r.started_at ? new Date(r.started_at).toLocaleString("ru-RU") : ""}</td>
                    <td>{r.name}</td>
                    <td><span className={jobStatusBadgeClass(r.status)}>{r.status}</span></td>
                    <td>{typeof r.duration_ms === "number" ? `${r.duration_ms} ms` : "—"}</td>
                    <td className="text-xs">{JSON.stringify(r.details)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="flex items-center justify-between pt-2">
              <div className="text-xs text-[hsl(var(--muted-foreground))]">Страница {runPage} / {pageCount(runTotal)}</div>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" disabled={runPage <= 1} onClick={() => setRunPage((p) => p - 1)}>Назад</Button>
                <Button size="sm" variant="outline" disabled={runPage >= pageCount(runTotal)} onClick={() => setRunPage((p) => p + 1)}>Далее</Button>
              </div>
            </div>
          </CardContent>
        </Card>
        )}

        {tab === "logs" && (
        <Card>
          <CardHeader>
            <CardTitle>Логи AI-агента</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {logs.map((l, i) => (
              <div key={i} className="border-b border-[hsl(var(--border))] pb-2">
                <div className="text-xs text-[hsl(var(--muted-foreground))]">{l.created_at}</div>
                <div>
                  <span className={logLevelBadgeClass(l.level)}>{l.level}</span> {l.message}
                </div>
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
      </div>
    </Shell>
  );
}
