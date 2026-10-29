/** API timestamps without an offset are stored in UTC. Display them in browser local time. */
export function formatLocalDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const timestamp = value.replace(" ", "T");
  const withZone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(timestamp)
    ? timestamp
    : `${timestamp}Z`;
  const date = new Date(withZone);
  return Number.isNaN(date.getTime())
    ? "—"
    : date.toLocaleString(undefined, {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      });
}
