import { describe, expect, it } from "vitest";

import { formatKopecks } from "./money.js";

describe("formatKopecks", () => {
  it("prints two fraction digits and no currency sign", () => {
    expect(formatKopecks(0)).toBe("0.00");
    expect(formatKopecks(5)).toBe("0.05");
    expect(formatKopecks(200)).toBe("2.00");
    expect(formatKopecks(12345)).toBe("123.45");
  });
});
