
export type SyntaxTag = {
  tag: string;
  count?: number | null;
  score?: number | null;
  reason?: string | null;
};

export type ConceptTag = {
  tag: string;
  count?: number | null;
  score?: number | null;
  reason?: string | null;
};

export type Suggestion = {
  type?: string;
  message?: string;
};

export type AnalysisResponse = {
  success: boolean;
  syntax_tags: SyntaxTag[];
  concept_tags: ConceptTag[];
  metrics: Record<string, number>;
  suggestions: Suggestion[];
  error?: string | null;
};

export type FinalStyleAnalysis = {
  syntax_tags: SyntaxTag[];
  concept_tags: ConceptTag[];
  metrics: Record<string, number>;
};

// ============================================================
// Runtime execution verification
// ============================================================

export type VerificationStatus =
  | "equivalent"
  | "different"
  | "not_verified";

export type ExecutionResult = {
  success: boolean;
  stdout: string;
  stderr: string;
  exit_code: number | null;
  timed_out: boolean;
  blocked: boolean;
  block_reason?: string | null;
};

// ============================================================
// Function test inputs
// ============================================================

// JSON으로 전송 가능한 함수 테스트 입력값입니다.
// 실제 지원 자료형과 중첩 깊이는 백엔드에서도 검사합니다.
export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

export type FunctionTestCase = {
  function: string;
  args?: JsonValue[];
  kwargs?: Record<string, JsonValue>;
};

// ============================================================
// Function return verification
// ============================================================

export type FunctionResultRecord = {
  kind: "value" | "exception" | "unsupported";
  value?: unknown;
  type?: string;
  message?: string;
  reason?: string;
};

export type FunctionCaseVerification = {
  function: string;
  args: JsonValue[];
  kwargs: Record<string, JsonValue>;
  status: VerificationStatus;
  equivalent: boolean | null;
  message: string;
  original_result?: FunctionResultRecord | null;
  transformed_result?: FunctionResultRecord | null;
  original_stdout?: string | null;
  transformed_stdout?: string | null;
};

export type FunctionVerification = {
  status: VerificationStatus;
  equivalent: boolean | null;
  cases: FunctionCaseVerification[];
  message: string;
};

// ============================================================
// Combined execution verification
// ============================================================

export type ExecutionVerification = {
  source: string;
  status: VerificationStatus;
  equivalent: boolean | null;

  original: ExecutionResult;
  transformed: ExecutionResult;

  message: string;

  // 기존 API 요청에서는 null일 수 있습니다.
  // 함수 테스트를 요청하면 검증 결과가 전달됩니다.
  function_verification?: FunctionVerification | null;
};

// ============================================================
// Saved coding style
// ============================================================

export interface CodingStyle {
  id: string;
  name: string;
  description: string;
  syntax_tags: SyntaxTag[];
  concept_tags: ConceptTag[];
  metrics: Record<string, number>;
  created_at: string;
}

// ============================================================
// Style application request
// ============================================================

export type StyleApplyRequest = {
  language: string;
  code: string;
  style: CodingStyle;

  // 지정하지 않으면 기존 실행 출력 비교만 수행합니다.
  function_cases?: FunctionTestCase[] | null;
};

// ============================================================
// Style application response
// ============================================================

export type StyleApplyResponse = {
  success: boolean;
  original_code: string;
  transformed_code: string;

  final_analysis?: FinalStyleAnalysis | null;

  missing_syntax_tags: SyntaxTag[];
  missing_concept_tags: ConceptTag[];

  execution_verification?: ExecutionVerification | null;

  summary?: string | null;
  applied_rules: string[];
  warnings: string[];

  error?: string | null;
};
