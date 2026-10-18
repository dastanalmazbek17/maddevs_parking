import { describe, expect, it } from "vitest";

import { errorMessage } from "./errors.js";

describe("errorMessage", () => {
  it("uses detail", () => {
    expect(errorMessage({ code: "no_free_place", detail: "Свободных мест нет." })).toBe(
      "Свободных мест нет.",
    );
  });

  it("uses field text ahead of the generic detail", () => {
    expect(
      errorMessage({
        code: "validation_error",
        detail: "Проверьте поля запроса.",
        fields: { email: "Пользователь с такой почтой уже есть." },
      }),
    ).toBe("Пользователь с такой почтой уже есть.");
  });

  it("joins a list of field errors", () => {
    expect(errorMessage({ fields: { password: ["Слишком короткий.", "Слишком простой."] } })).toBe(
      "Слишком короткий. Слишком простой.",
    );
  });

  it("falls back when the body is empty", () => {
    expect(errorMessage(null)).toBe("Запрос не выполнен.");
    expect(errorMessage({ fields: {} })).toBe("Запрос не выполнен.");
  });
});
