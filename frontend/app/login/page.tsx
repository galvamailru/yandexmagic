"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetch, getToken, setToken } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [devLoading, setDevLoading] = useState(false);

  useEffect(() => {
    if (getToken()) router.replace("/dashboard");
  }, [router]);

  async function startOAuth() {
    setLoading(true);
    try {
      const data = await apiFetch<{ url: string }>("/api/auth/yandex/url");
      window.location.href = data.url;
    } catch {
      try {
        await loginWithDevToken();
      } catch (e) {
        toast.error(
          `Не удалось получить URL OAuth. ${String(e)}`
        );
      }
    } finally {
      setLoading(false);
    }
  }

  async function loginWithDevToken() {
    setDevLoading(true);
    try {
      const dev = await apiFetch<{ access_token: string }>("/api/auth/dev-token", { method: "POST" });
      setToken(dev.access_token);
      toast.success("Dev-вход выполнен");
      router.replace("/dashboard");
    } finally {
      setDevLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-gradient-to-br from-slate-50 via-white to-blue-50">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-2xl">Вход через Яндекс</CardTitle>
          <p className="text-sm text-[hsl(var(--muted-foreground))]">
            Используется OAuth со scope <code className="text-xs">direct:api</code>
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <Button className="w-full" onClick={startOAuth} disabled={loading || devLoading}>
            {loading ? "Переход…" : "Войти с Яндекс"}
          </Button>
          <Button
            className="w-full"
            variant="outline"
            onClick={loginWithDevToken}
            disabled={loading || devLoading}
          >
            {devLoading ? "Вход..." : "Dev вход (без OAuth)"}
          </Button>
          <p className="text-xs text-[hsl(var(--muted-foreground))]">
            Если OAuth не настроен, бэкенд попробует скрытый dev-token (только без YANDEX_CLIENT_ID).
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
