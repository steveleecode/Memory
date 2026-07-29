import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { SpatialRenderBoundary } from "./MemoryFoundation";

function renderNode(node: ReactNode) {
  return renderToStaticMarkup(<>{node}</>);
}

describe("SpatialRenderBoundary", () => {
  it("renders the fallback after a child render error", () => {
    const boundary = new SpatialRenderBoundary({
      children: <span>graph</span>,
      fallback: <span>fallback map</span>,
      resetKey: "a",
    });

    boundary.state = SpatialRenderBoundary.getDerivedStateFromError();

    expect(renderNode(boundary.render())).toContain("fallback map");
  });

  it("preserves fallback state when the reset key is unchanged", () => {
    const boundary = new SpatialRenderBoundary({
      children: <span>graph</span>,
      fallback: <span>fallback map</span>,
      resetKey: "a",
    });
    boundary.state = { hasError: true };
    const setState = vi.fn();
    boundary.setState = setState;

    boundary.componentDidUpdate({ resetKey: "a" });

    expect(setState).not.toHaveBeenCalled();
    expect(renderNode(boundary.render())).toContain("fallback map");
  });

  it("retries rendering when the reset key changes", () => {
    const boundary = new SpatialRenderBoundary({
      children: <span>graph</span>,
      fallback: <span>fallback map</span>,
      resetKey: "b",
    });
    boundary.state = { hasError: true };
    boundary.setState = (nextState) => {
      const stateUpdate =
        typeof nextState === "function" ? nextState(boundary.state, boundary.props) : nextState;
      boundary.state = { ...boundary.state, ...stateUpdate };
    };

    boundary.componentDidUpdate({ resetKey: "a" });

    expect(boundary.state.hasError).toBe(false);
    expect(renderNode(boundary.render())).toContain("graph");
  });
});
