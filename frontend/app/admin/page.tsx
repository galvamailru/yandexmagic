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
type Paged<T> = { items: T[]; total: number; page: number; limit: number };

export default function AdminPage() {
  const router = useRouter();
  const [rows, setRows] = useState<Tenant[]>([]);
  const [logs, setLogs] = useState<{ message: string; level: string; created_at: string | null }[]>([]);
  const [runs, setRuns] = useState<JobRun[]>([]);
  const [prompt, setPrompt] = useState("");
  const [savingPrompt, setSavingPrompt] = useState(false);
  const [normalizing, setNormalizing] = useState(false);
  const [creatingSandbox, setCreatingSandbox] = useState(false);
  const [sandboxName, setSandboxName] = useState("Sandbox tenant");
  const [roleForm, setRoleForm] = useState({ tenantId: "", userId: "", role: "manager" });
  const [savingRole, setSavingRole] = useState(false);
  const [tab, setTab] = useState<"tenants" | "jobs" | "logs">("tenants");
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
        const p = await apiFetch<{ prompt: string }>("/api/admin/ai-prompt");
        setPrompt(p.prompt || "");
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

  async function savePrompt() {
    setSavingPrompt(true);
    try {
      await apiFetch("/api/admin/ai-prompt", {
        method: "PUT",
        body: JSON.stringify({ prompt }),
      });
      toast.success("Промпт сохранён");
    } catch (e) {
      toast.error(String(e));
    } finally {
      setSavingPrompt(false);
    }
  }

  async function normalizeRecs() {
    setNormalizing(true);
    try {
      const res = await apiFetch<{ report: Array<{ tenant: string; normalized: number; split_created: number }> }>(
        "/api/admin/normalize-recommendations",
        { method: "POST" }
      );
      const totalNorm = res.report.reduce((a, x) => a + (x.normalized || 0), 0);
      const totalSplit = res.report.reduce((a, x) => a + (x.split_created || 0), 0);
      toast.success(`Нормализация завершена: обновлено ${totalNorm}, создано доп. рекомендаций ${totalSplit}`);
    } catch (e) {
      toast.error(String(e));
    } finally {
      setNormalizing(false);
    }
  }

  async function createSandbox() {
    setCreatingSandbox(true);
    try {
      const res = await apiFetch<{ tenant_id: string }>("/api/admin/create-sandbox?name=" + encodeURIComponent(sandboxName), {
        method: "POST",
      });
      toast.success(`Sandbox создан: ${res.tenant_id}`);
      const t = await apiFetch<Paged<Tenant>>(`/api/admin/tenants?page=${tenantPage}&limit=${pageSize}`);
      setRows(t.items);
      setTenantTotal(t.total);
    } catch (e) {
      toast.error(String(e));
    } finally {
      setCreatingSandbox(false);
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
              Job runs
            </Button>
            <Button variant={tab === "logs" ? "default" : "outline"} size="sm" onClick={() => setTab("logs")}>
              Логи
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

        <Card>
          <CardHeader>
            <CardTitle>Sandbox и роли</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-col md:flex-row gap-2">
              <Input value={sandboxName} onChange={(e) => setSandboxName(e.target.value)} placeholder="Название sandbox tenant" />
              <Button onClick={createSandbox} disabled={creatingSandbox}>
                {creatingSandbox ? "Создаём..." : "Создать sandbox"}
              </Button>
            </div>
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

        <Card>
          <CardHeader>
            <CardTitle>Промпт AI-агента (DeepSeek)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <textarea
              className="w-full min-h-52 rounded-md border border-[hsl(var(--border))] p-3 text-sm"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Введите system prompt для агента..."
            />
            <div className="flex gap-2">
              <Button onClick={savePrompt} disabled={savingPrompt}>
                {savingPrompt ? "Сохраняем..." : "Сохранить промпт"}
              </Button>
              <Button variant="outline" onClick={normalizeRecs} disabled={normalizing}>
                {normalizing ? "Нормализуем..." : "Нормализовать старые рекомендации"}
              </Button>
            </div>
          </CardContent>
        </Card>

        {tab === "jobs" && (
        <Card>
          <CardHeader>
            <CardTitle>Job runs</CardTitle>
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
