import { describe, expect, it } from "vitest";
import { Button, MemoryFoundation, StatusPill, tokens } from "./index";

describe("public UI exports", () => {
  it("exports stable components and design tokens", () => {
    expect(Button).toBeTypeOf("function");
    expect(MemoryFoundation).toBeTypeOf("function");
    expect(StatusPill).toBeTypeOf("function");
    expect(tokens.color.accent).toBe("#1f6f68");
    expect(tokens.radius.md).toBe("8px");
  });
});
