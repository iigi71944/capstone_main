import type { editor } from "monaco-editor";

export interface HighlightItem {
  startLine: number;
  startColumn: number;
  endLine: number;
  endColumn: number;
  kind: string;
  label: string;
}

/* 블록 전체 스타일 */
function getBlockClassName(kind: string): string {
  switch (kind) {
    case "function-block":
      return "monaco-highlight-block monaco-highlight-function";
    case "loop-block":
      return "monaco-highlight-block monaco-highlight-loop";
    case "if-block":
      return "monaco-highlight-block monaco-highlight-if";
    default:
      return "monaco-highlight-block monaco-highlight-default";
  }
}

/* 시작 줄 강조 */
function getLineClassName(kind: string): string {
  switch (kind) {
    case "function-block":
      return "monaco-highlight-line monaco-highlight-line-function";
    case "loop-block":
      return "monaco-highlight-line monaco-highlight-line-loop";
    case "if-block":
      return "monaco-highlight-line monaco-highlight-line-if";
    default:
      return "monaco-highlight-line monaco-highlight-line-default";
  }
}

/* 왼쪽 컬러 바 */
function getGlyphClassName(kind: string): string {
  switch (kind) {
    case "function-block":
      return "monaco-highlight-glyph monaco-highlight-glyph-function";
    case "loop-block":
      return "monaco-highlight-glyph monaco-highlight-glyph-loop";
    case "if-block":
      return "monaco-highlight-glyph monaco-highlight-glyph-if";
    default:
      return "monaco-highlight-glyph monaco-highlight-glyph-default";
  }
}

/* 핵심: decoration 생성 */
export function buildDecorations(
  monaco: typeof import("monaco-editor"),
  highlights: HighlightItem[]
): editor.IModelDeltaDecoration[] {
  return highlights.flatMap((item) => {
    const startColumn = Math.max(1, item.startColumn);
    const endColumn = Math.max(startColumn + 1, item.endColumn);

    /* 1️⃣ 블록 전체 배경 */
    const blockDecoration: editor.IModelDeltaDecoration = {
      range: new monaco.Range(
        item.startLine,
        startColumn,
        item.endLine,
        endColumn
      ),
      options: {
        className: getBlockClassName(item.kind),
        isWholeLine: false,
        overviewRuler: {
          position: 2,
          color:
            item.kind === "function-block"
              ? "rgba(59, 130, 246, 0.9)"
              : item.kind === "loop-block"
              ? "rgba(34, 197, 94, 0.9)"
              : item.kind === "if-block"
              ? "rgba(234, 179, 8, 0.9)"
              : "rgba(148, 163, 184, 0.9)",
        },
      },
    };

    /* 2️⃣ 시작 줄 강조 + hover 라벨 */
    const lineDecoration: editor.IModelDeltaDecoration = {
      range: new monaco.Range(item.startLine, 1, item.startLine, 1),
      options: {
        isWholeLine: true,
        firstLineDecorationClassName: getLineClassName(item.kind),
        glyphMarginClassName: getGlyphClassName(item.kind),

        // 👉 hover 시 설명만 표시 (라벨 텍스트 제거됨)
        glyphMarginHoverMessage: [{ value: item.label }],
        linesDecorationsTooltip: item.label,

        stickiness:
          monaco.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges,
      },
    };

    return [blockDecoration, lineDecoration];
  });
}