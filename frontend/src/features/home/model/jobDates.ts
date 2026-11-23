/** How a job's dates read on the public board. Pure. */


export function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const hours = Math.floor(diffMs / 3_600_000);
  if (hours < 1) return "Just posted";
  if (hours < 24) return `Posted ${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `Posted ${days}d ago`;
}

export function daysUntil(dateStr: string): number {
  return Math.ceil((new Date(dateStr).getTime() - Date.now()) / 86_400_000);
}

export function deadlineLabel(dateStr: string): string {
  const diffDays = daysUntil(dateStr);
  if (diffDays < 0) return "Applications closed";
  if (diffDays === 0) return "Closes today";
  if (diffDays === 1) return "Closes in 1 day";
  return `Closes in ${diffDays} days`;
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}
