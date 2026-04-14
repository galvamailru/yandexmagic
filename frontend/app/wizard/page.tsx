"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Shell } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch, getToken } from "@/lib/api";

export default function WizardPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [me, setMe] = useState<{ is_platform_admin: boolean } | null>(null);
  const [form, setForm] = useState({ site_url: "", budget_rub: 5000, geo: "Москва", goal: "Лиды" });
  const [ads, setAds] = useState<Record<string, string>[]>([]);
  const [risk, setRisk] = useState(false);

  useEffect(() => {
    if (!getToken()) router.replace("/login");
  }, [router]);

  useEffect(() => {
    (async () => {
      try {
        const u = await apiFetch<{ is_platform_admin: boolean }>("/api/me");
        setMe(u);
      } catch {
        /* ignore */
      }
    })();
  }, []);

  async function submit1() {
    await apiFetch("/api/wizard/step1", { method: "POST", body: JSON.stringify(form) });
    setStep(2);
    toast.success("Шаг 1 сохранён");
  }

  async function run2() {
    const res = await apiFetch<{ ads: Record<string, string>[] }>("/api/wizard/step2", { method: "POST" });
    setAds(res.ads || []);
    setStep(3);
    toast.success("Ключи и объявления готовы");
  }

  async function submit3() {
    await apiFetch("/api/wizard/step3", { method: "POST", body: JSON.stringify({ ads }) });
    setStep(4);
    toast.success("Черновик сохранён");
  }

  async function launch() {
    await apiFetch("/api/wizard/launch", {
      method: "POST",
      body: JSON.stringify({ accept_autopilot_risk: risk }),
    });
    toast.success("Кампания создана в Директе");
    router.push("/campaigns");
  }

  if (!me) return null;

  return (
    <Shell isAdmin={me.is_platform_admin}>
      <div className="max-w-3xl mx-auto space-y-6">
        <div>
          <h1 className="text-3xl font-semibold">Мастер кампании</h1>
          <p className="text-[hsl(var(--muted-foreground))]">4 шага до запуска</p>
        </div>

        {step === 1 && (
          <Card>
            <CardHeader>
              <CardTitle>Шаг 1 — параметры</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <label className="text-sm font-medium block">URL сайта</label>
              <Input placeholder="https://site.ru" value={form.site_url} onChange={(e) => setForm({ ...form, site_url: e.target.value })} />
              <label className="text-sm font-medium block">Бюджет в день (₽)</label>
              <Input
                type="number"
                placeholder="Бюджет в день, ₽"
                value={form.budget_rub}
                onChange={(e) => setForm({ ...form, budget_rub: Number(e.target.value) })}
              />
              <label className="text-sm font-medium block">География показов</label>
              <Input placeholder="Гео" value={form.geo} onChange={(e) => setForm({ ...form, geo: e.target.value })} />
              <label className="text-sm font-medium block">Цель кампании</label>
              <Input placeholder="Цель" value={form.goal} onChange={(e) => setForm({ ...form, goal: e.target.value })} />
              <Button onClick={submit1}>Далее</Button>
            </CardContent>
          </Card>
        )}

        {step === 2 && (
          <Card>
            <CardHeader>
              <CardTitle>Шаг 2 — AI сбор ключей</CardTitle>
            </CardHeader>
            <CardContent>
              <Button onClick={run2}>Запустить парсинг и Вордстат</Button>
            </CardContent>
          </Card>
        )}

        {step === 3 && (
          <Card>
            <CardHeader>
              <CardTitle>Шаг 3 — редактирование объявлений</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {ads.map((a, i) => (
                <div key={i} className="grid gap-2 border rounded-lg p-3">
                  <label className="text-sm font-medium">Заголовок 1</label>
                  <Input value={a.title || ""} onChange={(e) => {
                    const n = [...ads]; n[i] = { ...n[i], title: e.target.value }; setAds(n);
                  }} />
                  <label className="text-sm font-medium">Заголовок 2</label>
                  <Input value={a.title2 || ""} onChange={(e) => {
                    const n = [...ads]; n[i] = { ...n[i], title2: e.target.value }; setAds(n);
                  }} />
                  <label className="text-sm font-medium">Текст объявления</label>
                  <Input value={a.text || ""} onChange={(e) => {
                    const n = [...ads]; n[i] = { ...n[i], text: e.target.value }; setAds(n);
                  }} />
                </div>
              ))}
              <Button onClick={submit3}>Далее</Button>
            </CardContent>
          </Card>
        )}

        {step === 4 && (
          <Card>
            <CardHeader>
              <CardTitle>Шаг 4 — запуск</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={risk} onChange={(e) => setRisk(e.target.checked)} />
                Я понимаю риски автопилота (изменение ставок и статусов фраз)
              </label>
              <Button onClick={launch} disabled={!risk}>
                Создать в Директе и включить автопилот
              </Button>
            </CardContent>
          </Card>
        )}
      </div>
    </Shell>
  );
}
