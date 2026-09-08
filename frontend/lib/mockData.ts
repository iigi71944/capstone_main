import { AnalysisResponse } from "../types/analysis";

export const mockAnalysis: AnalysisResponse = {
  syntax_tags: [
    { tag: "함수 정의", count: 1 },
    { tag: "for문", count: 1 },
    { tag: "if문", count: 1 },
    { tag: "리스트 사용", count: 1 },
  ],
  concept_tags: [
    { tag: "인덱스 기반 순회", score: 0.91 },
    { tag: "절차형 스타일", score: 0.78 },
    { tag: "조건문 활용", score: 0.72 },
  ],
  metrics: {
    function_count: 1,
    loop_count: 1,
    if_count: 1,
    max_nesting_depth: 2,
    index_loop_count: 1,
    direct_loop_count: 0,
  },
  highlights: [
  {
    startLine: 1,
    startColumn: 1,
    endLine: 6,
    endColumn: 18,
    kind: "function-block",
    label: "함수 정의",
  },
  {
    startLine: 3,
    startColumn: 1,
    endLine: 5,
    endColumn: 30,
    kind: "loop-block",
    label: "for문",
  },
  {
    startLine: 4,
    startColumn: 1,
    endLine: 5,
    endColumn: 30,
    kind: "if-block",
    label: "if문",
  },
],
  suggestions: [
    {
      type: "style",
      message: "for i in range(len(nums)) 대신 직접 순회를 사용하면 가독성이 좋아질 수 있습니다.",
    },
    {
      type: "readability",
      message: "조건문 내부 로직이 길어질 경우 별도 함수로 분리하는 방식을 고려해보세요.",
    },
  ],
};