// CAPSTONE_FORMATTING_STYLE_GIT_ALIGNED_V2: 분석 및 저장 서식 프로필 타입

export type SyntaxTag = {
  tag: string;
  count?: number | null;
  score?: number | null;
  reason?: string | null;
};

export type ConceptTag = {
  tag: string;
  details?: Record<string, unknown> | null; // CAPSTONE_FORMAT_CONCEPT_TYPES_V1
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
  formatting_style?: Record<string, unknown>;
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
  stdin?: string | null; // optional case-specific stdin
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

export type StdinCaseVerification = {
  case_number: number;
  stdin: string;
  status: VerificationStatus;
  equivalent: boolean | null;
  original: ExecutionResult;
  transformed: ExecutionResult;
  message: string;
};

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
  stdin_case_results?: StdinCaseVerification[] | null;
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
  /** CAPSTONE_BATCH35_4_METRIC_VERSION_V1: absent for historical saved styles. */
  metrics_version?: number;
  formatting_style?: Record<string, unknown>;
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
  // CAPSTONE_BATCH16_STRICT_VERIFY_V1: optional for backward compatibility.
  strict_runtime_validation?: boolean;
  // CAPSTONE_BATCH17_STDIN_V1: optional shared input text.
  stdin?: string | null;
  stdin_cases?: string[] | null;
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
