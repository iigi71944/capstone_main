import {
  AnalysisResponse,
  CodingStyle,
  StyleApplyResponse,
} from "../types/analysis";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export async function analyzeCode(code: string): Promise<AnalysisResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/analyze`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      language: "python",
      code,
    }),
  });

  if (!response.ok) {
    throw new Error("백엔드 분석 요청에 실패했습니다.");
  }

  const data: AnalysisResponse = await response.json();
  return data;
}

export async function applyCodingStyle(
  code: string,
  style: CodingStyle
): Promise<StyleApplyResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/apply-style`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      language: "python",
      code,
      style,
    }),
  });

  if (!response.ok) {
    throw new Error("코딩 스타일 적용 요청에 실패했습니다.");
  }

  const data: StyleApplyResponse = await response.json();
  return data;
}