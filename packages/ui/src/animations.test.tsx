import type { EffectCallback } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

const gsapMock = vi.hoisted(() => ({
  context: vi.fn((callback: () => void) => {
    callback();
    return { revert: vi.fn() };
  }),
  fromTo: vi.fn(),
}));

const layoutEffectMock = vi.hoisted(() => vi.fn((effect: EffectCallback) => effect()));

vi.mock("gsap", () => ({ gsap: gsapMock }));
vi.mock("react", async () => {
  const actual = await vi.importActual<typeof import("react")>("react");
  return { ...actual, useLayoutEffect: layoutEffectMock };
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

function isCleanup(value: unknown): value is () => void {
  return typeof value === "function";
}

describe("animation helpers", () => {
  it("detects reduced motion defensively", async () => {
    const { prefersReducedMotion } = await import("./animations");

    vi.stubGlobal("window", { matchMedia: vi.fn(() => ({ matches: true })) });
    expect(prefersReducedMotion()).toBe(true);

    vi.stubGlobal("window", {});
    expect(prefersReducedMotion()).toBe(false);
  });

  it("runs press animation only when motion is allowed", async () => {
    const { pressElement } = await import("./animations");
    const target = {} as Element;

    vi.stubGlobal("window", { matchMedia: vi.fn(() => ({ matches: false })) });
    pressElement(target);
    expect(gsapMock.fromTo).toHaveBeenCalledWith(
      target,
      { scale: 0.985 },
      expect.objectContaining({ scale: 1 }),
    );

    gsapMock.fromTo.mockClear();
    vi.stubGlobal("window", { matchMedia: vi.fn(() => ({ matches: true })) });
    pressElement(target);
    expect(gsapMock.fromTo).not.toHaveBeenCalled();
  });

  it("runs panel and list entrance animations with scoped cleanup", async () => {
    const { useEntranceMotion } = await import("./animations");
    const cleanup: { current: unknown } = { current: undefined };
    const revert = vi.fn();
    gsapMock.context.mockImplementationOnce((callback: () => void) => {
      callback();
      return { revert };
    });
    layoutEffectMock.mockImplementationOnce((effect: EffectCallback) => {
      cleanup.current = effect();
    });

    vi.stubGlobal("window", { matchMedia: vi.fn(() => ({ matches: false })) });
    const element = {
      querySelectorAll: vi.fn(() => ["a", "b"]),
    } as unknown as HTMLElement;

    useEntranceMotion({ current: element }, "list", ["key"]);

    expect(gsapMock.context).toHaveBeenCalledWith(expect.any(Function), element);
    expect(gsapMock.fromTo).toHaveBeenCalledWith(
      ["a", "b"],
      { autoAlpha: 0, y: 10 },
      expect.objectContaining({ stagger: 0.035 }),
    );

    if (isCleanup(cleanup.current)) {
      cleanup.current();
    }
    expect(revert).toHaveBeenCalled();
  });
});
