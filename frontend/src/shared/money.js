/** Integer kopecks as a decimal with two fraction digits. No currency sign. */
export function formatKopecks(kopecks) {
  const value = Number(kopecks);
  if (!Number.isFinite(value)) return "";
  const sign = value < 0 ? "-" : "";
  const absolute = Math.trunc(Math.abs(value));
  const major = Math.trunc(absolute / 100);
  const minor = String(absolute % 100).padStart(2, "0");
  return `${sign}${major}.${minor}`;
}
