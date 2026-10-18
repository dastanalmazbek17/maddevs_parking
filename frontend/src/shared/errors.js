/** One sentence from {"detail"} or {"fields"}. */
export function errorMessage(payload) {
  if (!payload || typeof payload !== "object") return "Запрос не выполнен.";
  if (payload.fields && typeof payload.fields === "object") {
    const parts = [];
    for (const value of Object.values(payload.fields)) {
      if (Array.isArray(value)) parts.push(...value.map(String));
      else if (value) parts.push(String(value));
    }
    const text = parts.join(" ").trim();
    if (text) return text;
  }
  if (typeof payload.detail === "string" && payload.detail.trim()) return payload.detail;
  return "Запрос не выполнен.";
}
