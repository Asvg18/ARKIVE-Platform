/** One page of a list the browser already holds. The page asked for is
 *  clamped, so a search that shrinks the list never strands the reader on
 *  a page that no longer exists. */
export function paginate<T>(rows: readonly T[], page: number, pageSize: number) {
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
  const current = Math.min(Math.max(0, page), pageCount - 1);
  return {
    pageCount,
    page: current,
    visible: rows.slice(current * pageSize, (current + 1) * pageSize),
  };
}

/** The noun for a count: "job" for 1, "jobs" for any other number. */
export function nounFor(count: number, singular: string, plural = `${singular}s`): string {
  return count === 1 ? singular : plural;
}
