"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { setToken } from "@/lib/api";
import { API } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";

export default function AuthCallbackPage() {
  const router = useRouter();
  const params = useSearchParams();
  const [msg, setMsg] = useState("Завершаем вход…");

  useEffect(() => {
    const code = params.get("code");
    if (!code) {
      toast.error("Нет code в callback");
      router.replace("/login");
      return;
    }
    (async () => {
      try {
        const res = await fetch(`${API}/api/auth/yandex/callback`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code }),
        });
        if (!res.ok) throw new Error(await res.text());
        const data = (await res.json()) as { access_token: string };
        setToken(data.access_token);
        toast.success("Вы вошли");
        router.replace("/dashboard");
      } catch (e) {
        setMsg("Ошибка входа");
        toast.error(String(e));
        router.replace("/login");
      }
    })();
  }, [params, router]);

  return (
    <div className="min-h-screen flex items-center justify-center p-8">
      <div className="space-y-3 w-full max-w-sm">
        <Skeleton className="h-8 w-48" />
        <p className="text-sm text-[hsl(var(--muted-foreground))]">{msg}</p>
      </div>
    </div>
  );
}
