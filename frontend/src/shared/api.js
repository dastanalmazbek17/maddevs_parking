import { errorMessage } from "./errors.js";

const TOKEN_KEY = "parking-token";

export function getToken() {
  return globalThis.localStorage?.getItem(TOKEN_KEY) ?? "";
}

export function setToken(token) {
  globalThis.localStorage?.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  globalThis.localStorage?.removeItem(TOKEN_KEY);
}

function notifyLogout() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event("parking-logout"));
  }
}

export async function request(path, { method = "GET", body, auth = true } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const token = getToken();
  if (auth && token) headers.Authorization = `Token ${token}`;

  let response;
  try {
    response = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error("Нет связи с сервером.");
  }

  if (response.status === 204) return null;
  const text = await response.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  if (response.status === 401) {
    clearToken();
    notifyLogout();
    throw new Error(errorMessage(payload) || "Нужна авторизация.");
  }
  if (!response.ok) throw new Error(errorMessage(payload));
  return payload;
}
