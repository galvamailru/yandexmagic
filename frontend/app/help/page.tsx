"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Shell } from "@/components/shell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { getToken, apiFetch } from "@/lib/api";
import { toast } from "sonner";

export default function HelpPage() {
  const router = useRouter();
  const [me, setMe] = useState<{ is_platform_admin: boolean } | null>(null);
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
        <Skeleton className="h-10 w-64" />
      </Shell>
    );
  }

  return (
    <Shell isAdmin={me.is_platform_admin}>
      <div className="max-w-5xl mx-auto space-y-6">
        <div>
          <h1 className="text-3xl font-semibold">Wiki / Help</h1>
          <p className="text-[hsl(var(--muted-foreground))]">Справка по работе с системой YandexMagic</p>
        </div>

        <Card>
          <CardHeader><CardTitle>Быстрый старт</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p>1) Подключите аккаунт Яндекса на странице входа или используйте dev-вход в режиме разработки.</p>
            <p>2) Создайте кампанию через "Новая кампания" и укажите цель, гео и бюджет.</p>
            <p>3) Выберите режим: мониторинг, советник или автопилот.</p>
            <p>4) Откройте "Рекомендации" для аналитики и применения действий.</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Режимы кампании</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p><b>Мониторинг</b> - только наблюдение за метриками, без изменений.</p>
            <p><b>Советник</b> - генерирует рекомендации, но изменения применяются вручную.</p>
            <p><b>Автопилот</b> - может применять действия автоматически по заданным правилам.</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Состояния и действия</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p><b>ON</b> - объект активен и может участвовать в показах.</p>
            <p><b>SUSPENDED</b> - объект приостановлен, показы не идут.</p>
            <p>В списке кампаний доступна кнопка "Пауза/Возобновить".</p>
            <p>Все изменения фиксируются в аудите (action history).</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Детальная аналитика</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p>В карточке кампании доступны вкладки: рекомендации, логи, аудит, ключевые слова и объявления.</p>
            <p>Для больших объемов данных используется пагинация (page/limit).</p>
            <p>На вкладках "Ключевые слова" и "Объявления" можно смотреть стоимость и основные показатели.</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Режим разработки</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p>При <b>YANDEX_MOCK=true</b> используются тестовые данные и эмуляция внешних ответов.</p>
            <p>При <b>YANDEX_MOCK=false</b> используются только реальные данные Яндекс API.</p>
            <p>Если не хватает прав или данных, проверьте OAuth-подключение и токены.</p>
          </CardContent>
        </Card>
      </div>
    </Shell>
  );
}
