import { cn } from "@/lib/utils";

export function statusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: "Ожидает применения",
    applied: "Применено",
    rejected: "Отклонено",
  };
  return map[status] || status;
}

export function kindLabel(kind: string): string {
  const map: Record<string, string> = {
    general: "Общий вывод",
    keyword: "Ключевая фраза",
    warning: "Риск",
    success: "Эффективно",
  };
  return map[kind] || kind;
}

export function statusBadgeClass(status: string): string {
  return cn(
    "inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium",
    status === "applied" && "border-emerald-200 bg-emerald-50 text-emerald-700",
    status === "pending" && "border-amber-200 bg-amber-50 text-amber-700",
    status !== "applied" && status !== "pending" && "border-slate-200 bg-slate-50 text-slate-700"
  );
}

export function kindBadgeClass(kind: string): string {
  return cn(
    "inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium",
    kind === "warning" && "border-rose-200 bg-rose-50 text-rose-700",
    kind === "success" && "border-emerald-200 bg-emerald-50 text-emerald-700",
    kind === "keyword" && "border-blue-200 bg-blue-50 text-blue-700",
    !["warning", "success", "keyword"].includes(kind) && "border-slate-200 bg-slate-50 text-slate-700"
  );
}
