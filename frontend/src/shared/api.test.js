import { afterEach, describe, expect, it, vi } from "vitest";

import { clearToken, getToken, request, setToken } from "./api.js";

function storage() {
  const bag = new Map();
  return {
    getItem: (key) => bag.get(key) ?? null,
    setItem: (key, value) => bag.set(key, String(value)),
    removeItem: (key) => bag.delete(key),
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("request", () => {
  it("sends the stored token and returns JSON", async () => {
    vi.stubGlobal("localStorage", storage());
    setToken("abc");
    const fetchImpl = vi.fn(async () => ({
      status: 200,
      ok: true,
      text: async () => JSON.stringify([{ id: 1 }]),
    }));
    vi.stubGlobal("fetch", fetchImpl);

    await expect(request("/api/spots/")).resolves.toEqual([{ id: 1 }]);
    expect(fetchImpl.mock.calls[0][1].headers.Authorization).toBe("Token abc");
  });

  it("turns a domain error into its detail", async () => {
    vi.stubGlobal("localStorage", storage());
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        status: 409,
        ok: false,
        text: async () => JSON.stringify({ code: "double_entry", detail: "Эта машина уже на парковке." }),
      })),
    );

    await expect(request("/api/gate/enter/", { method: "POST", body: { plate: "A1" }, auth: false })).rejects.toThrow(
      "Эта машина уже на парковке.",
    );
  });

  it("logs out on 401", async () => {
    vi.stubGlobal("localStorage", storage());
    setToken("stale");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        status: 401,
        text: async () => JSON.stringify({ code: "not_authenticated", detail: "Нужна авторизация." }),
      })),
    );

    await expect(request("/api/me/")).rejects.toThrow("Нужна авторизация.");
    expect(getToken()).toBe("");
    clearToken();
  });

  it("reports a network failure", async () => {
    vi.stubGlobal("localStorage", storage());
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("offline");
      }),
    );

    await expect(request("/api/spots/", { auth: false })).rejects.toThrow("Нет связи с сервером.");
  });
});
