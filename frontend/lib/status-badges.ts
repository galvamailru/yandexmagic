export function campaignStateBadgeClass(state: string): string {
  if (state === "ON") return "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-emerald-100 text-emerald-700";
  if (state === "SUSPENDED") return "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-amber-100 text-amber-700";
  return "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-slate-100 text-slate-700";
}

export function campaignStateLabel(state: string): string {
  if (state === "ON") return "Активна";
  if (state === "SUSPENDED") return "Пауза";
  return state || "Неизвестно";
}

export function logLevelBadgeClass(level: string): string {
  const x = (level || "").toLowerCase();
  if (x === "error") return "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-rose-100 text-rose-700";
  if (x === "warning" || x === "warn") return "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-amber-100 text-amber-700";
  return "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-sky-100 text-sky-700";
}

export function jobStatusBadgeClass(status: string): string {
  const x = (status || "").toLowerCase();
  if (x === "success" || x === "ok" || x === "done") return "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-emerald-100 text-emerald-700";
  if (x === "failed" || x === "error") return "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-rose-100 text-rose-700";
  return "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-slate-100 text-slate-700";
}

export function tenantBlockedBadgeClass(blocked: boolean): string {
  return blocked
    ? "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-rose-100 text-rose-700"
    : "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-emerald-100 text-emerald-700";
}
