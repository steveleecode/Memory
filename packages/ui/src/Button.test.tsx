import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Button } from "./Button";

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
});
