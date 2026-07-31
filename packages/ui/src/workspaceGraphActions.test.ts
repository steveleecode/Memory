import { describe, expect, it, vi } from "vitest";
import { revealGraphSelection } from "./workspaceGraphActions";

describe("revealGraphSelection", () => {
  it("selects the file, switches to spatial view, clears hover, and resets the graph camera", () => {
    const actions = {
      setHoveredId: vi.fn(),
      setSelectedId: vi.fn(),
      setViewMode: vi.fn(),
      resetGraphView: vi.fn(),
    };

    revealGraphSelection("doc-1", actions);

    expect(actions.setSelectedId).toHaveBeenCalledWith("doc-1");
    expect(actions.setHoveredId).toHaveBeenCalledWith(null);
    expect(actions.setViewMode).toHaveBeenCalledWith("space");
    expect(actions.resetGraphView).toHaveBeenCalled();
  });
});
