"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Shell } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetch, getToken, setToken } from "@/lib/api";

type Tenant = { id: string; name: string; schema_name: string; is_blocked: boolean };

export default function AdminPage() {
  const router = useRouter();
  const [rows, setRows] = useState<Tenant[]>([]);
  const [logs, setLogs] = useState<{ message: string; level: string; created_at: string | null }[]>([]);
  const [prompt, setPrompt] = useState("");
  const [savingPrompt, setSavingPrompt] = useState(false);

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
        const t = await apiFetch<Tenant[]>("/api/admin/tenants");
        setRows(t);
        const l = await apiFetch<{ message: string; level: string; created_at: string | null }[]>("/api/admin/agent-logs?limit=50");
        setLogs(l);
        const p = await apiFetch<{ prompt: string }>("/api/admin/ai-prompt");
        setPrompt(p.prompt || "");
      } catch (e) {
        toast.error(String(e));
      }
    })();
  }, [router]);

  async function enter(id: string) {
    const tok = await apiFetch<{ access_token: string }>(`/api/admin/switch-tenant?tenant_id=${id}`, { method: "POST" });
    setToken(tok.access_token);
    toast.success("Контекст переключён");
    router.push("/dashboard");
  }

  async function block(id: string, blocked: boolean) {
    await apiFetch(`/api/admin/tenants/${id}/block?blocked=${blocked}`, { method: "POST" });
    toast.success(blocked ? "Тенант заблокирован" : "Тенант разблокирован");
    const t = await apiFetch<Tenant[]>("/api/admin/tenants");
    setRows(t);
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

  return (
    <Shell isAdmin>
      <div className="max-w-6xl mx-auto space-y-8">
        <div>
          <h1 className="text-3xl font-semibold">Админ-панель</h1>
          <p className="text-[hsl(var(--muted-foreground))]">Тенанты и логи агента</p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Тенанты</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {rows.map((t) => (
              <div key={t.id} className="flex items-center justify-between border rounded-lg p-3">
                <div>
                  <div className="font-medium">{t.name}</div>
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
            <Button onClick={savePrompt} disabled={savingPrompt}>
              {savingPrompt ? "Сохраняем..." : "Сохранить промпт"}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Логи AI-агента</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {logs.map((l, i) => (
              <div key={i} className="border-b border-[hsl(var(--border))] pb-2">
                <div className="text-xs text-[hsl(var(--muted-foreground))]">{l.created_at}</div>
                <div>
                  [{l.level}] {l.message}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </Shell>
  );
}
