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
          <CardHeader><CardTitle>Кому что доступно (роли)</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p><b>Owner</b> - управляет тенантом, людьми, политикой изменений и критичными действиями.</p>
            <p><b>Manager</b> - ведет кампании, работает с рекомендациями и настройками агента в ежедневном режиме.</p>
            <p><b>Viewer</b> - смотрит аналитику, логи и результаты, но не применяет изменения.</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Сценарий 1: Запуск новой кампании</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p>1) Перейдите в <b>Новая кампания</b> и заполните цель, гео, бюджет и исходные данные.</p>
            <p>2) Дождитесь подготовки ключей и объявлений, проверьте их визуально.</p>
            <p>3) Выберите режим работы:</p>
            <p>- <b>Мониторинг</b>: только наблюдение;</p>
            <p>- <b>Советник</b>: система предлагает, вы подтверждаете;</p>
            <p>- <b>Автопилот</b>: система может применять действия автоматически.</p>
            <p>4) После запуска откройте карточку кампании и проверьте вкладки: Ключевые слова, Объявления, Рекомендации.</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Сценарий 2: Ежедневная работа менеджера</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p>1) Откройте <b>Дашборд</b> и оцените динамику: расход, долю автопилота, применяемость рекомендаций.</p>
            <p>2) Перейдите в <b>Кампании</b>, отсортируйте приоритетные и откройте нужную карточку.</p>
            <p>3) На вкладке <b>Рекомендации</b> выберите релевантные пункты и примените группой.</p>
            <p>4) При необходимости обновите статусы рекомендаций (например, отклонено/ожидает).</p>
            <p>5) Проверьте вкладку <b>Аудит</b>, чтобы подтвердить, что изменения применились корректно.</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Сценарий 3: Контроль рисков и качества</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p>1) Перед включением автопилота начните с dry-run и посмотрите <b>Предпросмотр</b> действий.</p>
            <p>2) Ограничьте число изменений за цикл, чтобы избежать резких колебаний.</p>
            <p>3) Если результат сомнительный, используйте паузу кампании и откат последнего действия.</p>
            <p>4) Любой спорный кейс проверяйте через Логи + Аудит + фактическую эффективность в Дашборде.</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Настройки агента (что означает каждое поле)</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p><b>CTR низкий порог</b> - если CTR ключа ниже этого значения и расход высокий, агент может рекомендовать/выполнять паузу.</p>
            <p><b>CTR высокий порог</b> - если CTR выше этого значения, агент может рекомендовать/выполнять повышение ставки.</p>
            <p><b>Порог расхода, ₽</b> - минимальный расход, после которого правило "низкий CTR" считается значимым.</p>
            <p><b>Коэфф. повышения ставки</b> - множитель для роста ставки (например, 1.10 = +10%).</p>
            <p><b>Лимит изменений/цикл</b> - максимум изменений за один запуск агента для защиты от массовых правок.</p>
            <p><b>Dry-run автопилота</b> - агент только показывает план действий без фактической отправки изменений в Яндекс.Директ.</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Сценарий 4: Работа руководителя / owner</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p>1) Откройте Admin и проверьте здоровье платформы во вкладках <b>Запуски задач</b> и <b>Логи</b>.</p>
            <p>2) Во вкладке <b>Промпт AI</b> задайте стандарты рекомендаций (тон, риск, ограничения).</p>
            <p>3) Во вкладке <b>Тенанты</b> управляйте ролями команды и доступом.</p>
            <p>4) Еженедельно контролируйте KPI автоматизации на Дашборде и корректируйте правила агента.</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Если что-то пошло не так</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p><b>Нет данных по кампаниям</b> - переподключите аккаунт, обновите страницу и проверьте доступы пользователя.</p>
            <p><b>Нет ожидаемых действий от автопилота</b> - проверьте режим кампании и пороги в настройках агента.</p>
            <p><b>Результат хуже ожидаемого</b> - временно остановите изменения и проверьте вкладки Предпросмотр и Аудит.</p>
            <p><b>Не хватает прав</b> - запросите у owner нужную роль для вашего сценария работы.</p>
          </CardContent>
        </Card>
      </div>
    </Shell>
  );
}
