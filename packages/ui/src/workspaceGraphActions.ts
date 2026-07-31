export type WorkspaceViewMode = "space" | "timeline" | "list";

export type GraphNavigationActions = {
  setHoveredId: (id: string | null) => void;
  setSelectedId: (id: string) => void;
  setViewMode: (mode: WorkspaceViewMode) => void;
  resetGraphView: () => void;
};

export function revealGraphSelection(id: string, actions: GraphNavigationActions) {
  actions.setSelectedId(id);
  actions.setHoveredId(null);
  actions.setViewMode("space");
  actions.resetGraphView();
}
