"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { apiFetch, setToken } from "@/lib/api";

export default function DevLoginPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  async function loginDev() {
    setLoading(true);
    try {
      const dev = await apiFetch<{ access_token: string }>("/api/auth/dev-token", {
        method: "POST",
      });
      setToken(dev.access_token);
      toast.success("Dev-вход выполнен");
      router.replace("/dashboard");
    } catch (e) {
      toast.error(`Dev-вход не удался: ${String(e)}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loginDev();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-gradient-to-br from-slate-50 via-white to-blue-50">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-2xl">Dev вход</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-[hsl(var(--muted-foreground))]">
            Пытаемся войти через <code>/api/auth/dev-token</code>.
          </p>
          <Button className="w-full" onClick={loginDev} disabled={loading}>
            {loading ? "Выполняется вход..." : "Повторить dev-вход"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
