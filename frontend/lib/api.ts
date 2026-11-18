
import type {
  AnalysisResponse,
  CodingStyle,
  ConceptTag,
  FunctionTestCase,
  StyleApplyRequest,
  StyleApplyResponse,
} from "../types/analysis";


const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8000";


/**
 * Python 코드를 분석합니다.
 *
 * 기존 문법 태그, 개념 태그 및 메트릭 분석 기능을 유지합니다.
 */
export async function analyzeCode(
  code: string
): Promise<AnalysisResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/analyze`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        language: "python",
        code,
      }),
    }
  );

  if (!response.ok) {
    throw new Error(
      "백엔드 분석 요청에 실패했습니다."
    );
  }

  const data: AnalysisResponse =
    await response.json();

  return data;
}


/**
 * 저장된 코딩 스타일을 Python 코드에 적용합니다.
 *
 * 기존 사용 방식:
 *   applyCodingStyle(code, style)
 *
 * 함수 반환값 검증 사용 방식:
 *   applyCodingStyle(code, style, [
 *     {
 *       function: "calculate",
 *       args: [5],
 *       kwargs: {},
 *     },
 *   ])
 *
 * functionCases가 지정되지 않으면 기존 실행 검증만 수행합니다.
 *
 * functionCases가 지정되면 백엔드에서:
 * 1. 스타일 적용 전후 코드를 실행합니다.
 * 2. 표준 출력과 종료 상태를 비교합니다.
 * 3. 동일한 입력값으로 지정된 함수를 실행합니다.
 * 4. 반환값과 자료형을 비교합니다.
 * 5. 결과가 다르면 원본 코드로 복원합니다.
 */
export async function applyCodingStyle(
  code: string,
  style: CodingStyle,
  functionCases?: FunctionTestCase[] | null,
  strictRuntimeValidation: boolean = false,
  stdin?: string,
  stdinCases?: string[]
): Promise<StyleApplyResponse> {
  const requestBody: StyleApplyRequest = {
    language: "python",
    code,
    style,
  };

  // 테스트 입력이 제공된 경우에만 요청에 포함합니다.
  // undefined 또는 null이면 기존 API 요청 형태를 유지합니다.
  if (functionCases != null) {
    requestBody.function_cases = functionCases;
  }

  // CAPSTONE_BATCH16_STRICT_VERIFY_V1: omit the field for existing clients.
  if (strictRuntimeValidation) {
    requestBody.strict_runtime_validation = true;
  }
  // CAPSTONE_BATCH17_STDIN_V1: omit shared stdin for legacy requests.
  if (stdin !== undefined) {
    requestBody.stdin = stdin;
  }
  // Optional batch stdin: each row is checked against the same code pair.
  if (stdinCases !== undefined && stdinCases.length > 0) {
    requestBody.stdin_cases = stdinCases;
  }

  const response = await fetch(
    `${API_BASE_URL}/api/v1/apply-style`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(requestBody),
    }
  );

  if (!response.ok) {
    throw new Error(
      "코딩 스타일 적용 요청에 실패했습니다."
    );
  }

  const data: StyleApplyResponse =
    await response.json();

  return data;
}


// CAPSTONE_FORMATTING_STYLE_GIT_ALIGNED_V2: 원래 analyzeCode와 동일 서버에 서식 분석을 요청합니다.
// CAPSTONE_FORMAT_CONCEPT_FETCH_V1
export async function analyzeFormattingStyle(
  code: string
): Promise<{ formatting_style: Record<string, unknown>; concept_tags: ConceptTag[] }> {
  const response = await fetch(`${API_BASE_URL}/api/v1/formatting-style`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  });
  if (!response.ok) throw new Error("서식 분석 요청에 실패했습니다.");
  const data: unknown = await response.json();
  if (!data || typeof data !== "object") {
    throw new Error("서식 분석 결과가 올바르지 않습니다.");
  }
  const result = data as { success?: boolean; formatting_style?: unknown; concept_tags?: unknown };
  if (result.success !== true || !result.formatting_style ||
      typeof result.formatting_style !== "object" ||
      Array.isArray(result.formatting_style)) {
    throw new Error("서식 분석이 정상적으로 완료되지 않았습니다.");
  }
  const conceptTags: ConceptTag[] = Array.isArray(result.concept_tags)
    ? result.concept_tags.filter((item: unknown): item is ConceptTag => (
        typeof item === "object" && item !== null &&
        typeof (item as Record<string, unknown>).tag === "string"
      ))
    : [];
  return {
    formatting_style: result.formatting_style as Record<string, unknown>,
    concept_tags: conceptTags,
  };
}
