import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { StatusPill } from "./StatusPill";

describe("StatusPill", () => {
  it("uses the neutral tone by default", () => {
    const html = renderToStaticMarkup(<StatusPill label="Ready" />);

    expect(html).toBe('<span class="memory-status-pill memory-status-pill--neutral">Ready</span>');
  });

  it("renders the requested semantic tone", () => {
    const html = renderToStaticMarkup(<StatusPill label="Indexing" tone="warning" />);

    expect(html).toBe(
      '<span class="memory-status-pill memory-status-pill--warning">Indexing</span>',
    );
  });
});
