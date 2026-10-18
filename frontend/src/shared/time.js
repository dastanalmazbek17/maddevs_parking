function pad(value) {
  return String(value).padStart(2, "0");
}

/** datetime-local value in the browser's zone. */
export function toDateTimeLocal(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** datetime-local value as ISO 8601 with the browser offset. */
export function localInputToIso(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const offset = -date.getTimezoneOffset();
  const sign = offset >= 0 ? "+" : "-";
  const absolute = Math.abs(offset);
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}${sign}${pad(Math.trunc(absolute / 60))}:${pad(absolute % 60)}`;
}

/** UTC timestamp shown in the browser's local zone. */
export function formatLocal(iso) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}
