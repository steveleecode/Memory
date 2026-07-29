import type { PointerEvent, ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Button } from "./Button";

const pressElementMock = vi.hoisted(() => vi.fn());

vi.mock("./animations", () => ({ pressElement: pressElementMock }));

afterEach(() => {
  vi.clearAllMocks();
});

type ButtonElement = ReactElement<{
  disabled?: boolean;
  onPointerDown: (event: PointerEvent<HTMLButtonElement>) => void;
}>;

function pointerEvent(overrides: Partial<PointerEvent<HTMLButtonElement>> = {}) {
  return {
    currentTarget: {} as HTMLButtonElement,
    defaultPrevented: false,
    ...overrides,
  } as PointerEvent<HTMLButtonElement>;
}

describe("Button", () => {
  it("renders secondary button markup by default", () => {
    const html = renderToStaticMarkup(<Button>Search</Button>);

    expect(html).toContain('class="memory-button memory-button--secondary"');
    expect(html).toContain('type="button"');
    expect(html).toContain("<span>Search</span>");
  });

  it("preserves explicit button type, variant, disabled state, and icon slot", () => {
    const html = renderToStaticMarkup(
      <Button disabled icon={<span aria-hidden="true">+</span>} type="submit" variant="primary">
        Add folder
      </Button>,
    );

    expect(html).toContain('class="memory-button memory-button--primary"');
    expect(html).toContain('type="submit"');
    expect(html).toContain("disabled");
    expect(html).toContain('class="memory-button__icon"');
    expect(html).toContain("<span>Add folder</span>");
  });

  it("supports icon-only controls without adding an empty label span", () => {
    const html = renderToStaticMarkup(
      <Button aria-label="Refresh" icon={<span aria-hidden="true">R</span>} variant="ghost" />,
    );

    expect(html).toContain('aria-label="Refresh"');
    expect(html).toContain('class="memory-button memory-button--ghost"');
    expect(html).not.toContain("<span></span>");
  });

  it("runs the shared press microinteraction after caller pointer handlers", () => {
    const onPointerDown = vi.fn();
    const element = Button({ onPointerDown, children: "Search" }) as ButtonElement;
    const event = pointerEvent();

    element.props.onPointerDown(event);

    expect(onPointerDown).toHaveBeenCalledWith(event);
    expect(pressElementMock).toHaveBeenCalledWith(event.currentTarget);
  });

  it("skips press motion when the button is disabled or the event was handled", () => {
    const disabled = Button({ disabled: true, children: "Sync" }) as ButtonElement;
    disabled.props.onPointerDown(pointerEvent());

    const handled = Button({ children: "Cancel" }) as ButtonElement;
    handled.props.onPointerDown(pointerEvent({ defaultPrevented: true }));

    expect(pressElementMock).not.toHaveBeenCalled();
  });
});
