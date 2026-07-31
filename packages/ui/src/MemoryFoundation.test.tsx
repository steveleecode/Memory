import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { SearchResultContract } from "@memory/types";
import { FileInspector, Preview, ResultFilters, SpatialRenderBoundary } from "./MemoryFoundation";

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

describe("ResultFilters", () => {
  it("renders visible result count and disables reset when filters are default", () => {
    const html = renderNode(
      <ResultFilters
        resultCount={3}
        sourceOptions={["Drive"]}
        typeOptions={["PDF"]}
        sourceFilter="all"
        typeFilter="all"
        sortMode="relevance"
        setSourceFilter={vi.fn()}
        setTypeFilter={vi.fn()}
        setSortMode={vi.fn()}
        reset={vi.fn()}
      />,
    );

    expect(html).toContain("3 visible");
    expect(html).toContain("Refine this memory space");
    expect(html).toContain("disabled");
  });

  it("enables reset when a filter is active and shows filtered-empty copy", () => {
    const html = renderNode(
      <ResultFilters
        resultCount={0}
        sourceOptions={["Drive"]}
        typeOptions={["PDF"]}
        sourceFilter="Drive"
        typeFilter="all"
        sortMode="relevance"
        setSourceFilter={vi.fn()}
        setTypeFilter={vi.fn()}
        setSortMode={vi.fn()}
        reset={vi.fn()}
      />,
    );

    expect(html).toContain("0 visible");
    expect(html).not.toContain("disabled");
  });
});

describe("Preview", () => {
  it("keeps indexed excerpts visible for PDF and spreadsheet files", () => {
    const pdf = renderNode(<Preview result={resultFixture({ type: "application/pdf" })} />);
    const sheet = renderNode(
      <Preview
        result={resultFixture({
          type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })}
      />,
    );

    expect(pdf).toContain("Indexed match excerpt");
    expect(sheet).toContain("Indexed match excerpt");
    expect(pdf).not.toContain("PDF content has been indexed");
    expect(sheet).not.toContain("Spreadsheet content is represented");
  });

  it("renders type-specific placeholders only when no excerpt is available", () => {
    const pdf = renderNode(
      <Preview result={resultFixture({ type: "application/pdf", matching_excerpts: [] })} />,
    );

    expect(pdf).toContain("PDF content has been indexed for search.");
  });
});

describe("FileInspector", () => {
  it("renders prioritized actions, connected files, and collapsed technical metadata", () => {
    const result = resultFixture({
      document_metadata: {
        drive_web_url: "https://drive.example/file",
        indexing_status: "indexed",
        relative_path: "Projects/Memory/brief.pdf",
        source_id: "source-1",
      },
      type: "application/pdf",
    });
    const related = [resultFixture({ document_id: "related-1", title: "Related brief" })];

    const html = renderNode(
      <FileInspector
        result={result}
        related={related}
        openResult={vi.fn()}
        revealInGraph={vi.fn()}
        close={vi.fn()}
        ask={vi.fn()}
      />,
    );

    expect(html).toContain("Open original");
    expect(html).toContain("Ask about this");
    expect(html).toContain("Reveal in graph");
    expect(html).toContain("Related brief");
    expect(html).toContain("Technical details");
    expect(html).toContain("https://drive.example/file");
  });
});

type ResultFixtureOverrides = Partial<SearchResultContract> & {
  document_metadata?: Record<string, unknown>;
};

function resultFixture(overrides: ResultFixtureOverrides = {}): SearchResultContract {
  const { document_metadata: documentMetadataOverride, ...contractOverrides } = overrides;
  const documentMetadata = documentMetadataOverride ?? {
    extension: "pdf",
    relative_path: "Projects/Memory/brief.pdf",
  };
  return {
    document_id: "doc-1",
    title: "Memory brief",
    type: "text/plain",
    score: 0.82,
    matching_excerpts: ["Indexed match excerpt"],
    source_metadata: {
      kind: "google_drive",
      display_name: "Drive",
      metadata: {},
      document_metadata: documentMetadata,
    },
    explanation: {
      final_score: 0.82,
      semantic_score: 0.8,
      text_score: 0.4,
      matched_representation_type: "document_text",
      has_extracted_text: true,
      signals: [
        {
          type: "document_text",
          score: 0.82,
          raw_semantic_score: 0.8,
          raw_text_score: 0.4,
          matched_content: "Indexed match excerpt",
          applied_weight: 1,
        },
      ],
    },
    ...contractOverrides,
  };
}
