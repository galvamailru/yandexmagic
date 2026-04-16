"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Shell } from "@/components/shell";
import { apiFetch, getToken } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type Me = {
  id: string;
  login: string;
  email: string | null;
  display_name: string | null;
  is_platform_admin: boolean;
  autopilot_risk_accepted_at: string | null;
};

type ClientLogin = { client_login: string | null };

export default function ProfilePage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [clientLogin, setClientLogin] = useState("");
  const [savingClientLogin, setSavingClientLogin] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    (async () => {
      try {
        const [u, cl] = await Promise.all([
          apiFetch<Me>("/api/me"),
          apiFetch<ClientLogin>("/api/campaigns/client-login"),
        ]);
        setMe(u);
        setClientLogin(cl.client_login || "");
      } catch (e) {
        toast.error(String(e));
      } finally {
        setLoading(false);
      }
    })();
  }, [router]);

  async function saveClientLogin() {
    setSavingClientLogin(true);
    try {
      const updated = await apiFetch<ClientLogin>("/api/campaigns/client-login", {
        method: "PUT",
        body: JSON.stringify({ client_login: clientLogin.trim() || null }),
      });
      setClientLogin(updated.client_login || "");
      toast.success("Client-Login сохранен");
    } catch (e) {
      toast.error(String(e));
    } finally {
      setSavingClientLogin(false);
    }
  }

  return (
    <Shell isAdmin={Boolean(me?.is_platform_admin)}>
      <div className="max-w-3xl mx-auto space-y-6">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Профиль</h1>
          <p className="text-[hsl(var(--muted-foreground))]">Данные пользователя и параметры доступа к Яндекс.Директ</p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Пользователь</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {loading ? (
              <p className="text-[hsl(var(--muted-foreground))]">Загрузка...</p>
            ) : (
              <>
                <div><span className="text-[hsl(var(--muted-foreground))]">ID:</span> {me?.id}</div>
                <div><span className="text-[hsl(var(--muted-foreground))]">Логин:</span> {me?.login || "—"}</div>
                <div><span className="text-[hsl(var(--muted-foreground))]">Имя:</span> {me?.display_name || "—"}</div>
                <div><span className="text-[hsl(var(--muted-foreground))]">Email:</span> {me?.email || "—"}</div>
                <div><span className="text-[hsl(var(--muted-foreground))]">Роль платформы:</span> {me?.is_platform_admin ? "Администратор" : "Пользователь"}</div>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Client-Login Яндекс.Директ</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-[hsl(var(--muted-foreground))]">
              Используется для агентских кабинетов. Оставьте пустым, если работаете не через агентский доступ.
            </p>
            <div className="flex gap-2">
              <Input
                value={clientLogin}
                onChange={(e) => setClientLogin(e.target.value)}
                placeholder="например: my_client_login"
              />
              <Button variant="outline" onClick={saveClientLogin} disabled={savingClientLogin || loading}>
                {savingClientLogin ? "Сохраняем..." : "Сохранить"}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </Shell>
  );
}
