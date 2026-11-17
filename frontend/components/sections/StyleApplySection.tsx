
"use client";

import { useRef, useState } from "react";

import CodeEditor from "../editor/CodeEditor";
import CodeViewer from "../editor/CodeViewer";
import FunctionReturnResults from "./FunctionReturnResults";
import { parseVerificationInputs } from "../../lib/verificationInputSelection";

import type {
  AnalysisResponse,
  CodingStyle,
  ConceptTag,
  ExecutionResult,
  FunctionTestCase,
  StyleApplyResponse,
  SyntaxTag,
  VerificationStatus,
} from "../../types/analysis";

type SharedCodingStyle = CodingStyle & {
  is_shared?: boolean;
  shared_from?: string;
  shared_at?: string;
};

interface StyleApplyResult {
  styleName: string;
  missingSyntaxTags: SyntaxTag[];
  missingConceptTags: ConceptTag[];
  targetAnalysis: AnalysisResponse;
  applyResponse: StyleApplyResponse;
}

interface StyleApplySectionProps {
  selectedStyleId: string;
  setSelectedStyleId: (value: string) => void;
  savedStyles: SharedCodingStyle[];
  selectedStyle?: SharedCodingStyle;
  targetCode: string;
  setTargetCode: (value: string) => void;
  handleApplyStyle: (
    functionCases?: FunctionTestCase[] | null,
    legacyVerificationOption?: boolean,
    stdin?: string
  ) => void | Promise<void>;
  styleApplyLoading: boolean;
  styleApplyResult: StyleApplyResult | null;
  setStyleApplyResult: (
    value: StyleApplyResult | null
  ) => void;
  editableTransformedCode: string;
  setEditableTransformedCode: (
    value: string
  ) => void;
}

interface FunctionTestDraft {
  id: number;
  functionName: string;
  argsText: string;
  kwargsText: string;
  stdinText: string;
}

const MAX_FUNCTION_CASES = 8;

const createFunctionDraft = (
  id: number
): FunctionTestDraft => ({
  id,
  functionName: "",
  argsText: "[]",
  kwargsText: "{}",
  stdinText: "",
});


function getStatusClass(
  status: VerificationStatus
): string {
  if (status === "equivalent") {
    return "border-green-200 bg-green-50 text-green-800";
  }

  if (status === "different") {
    return "border-red-200 bg-red-50 text-red-800";
  }

  return "border-amber-200 bg-amber-50 text-amber-800";
}

function ExecutionOutput({
  result,
  emptyMessage,
}: {
  result?: ExecutionResult;
  emptyMessage: string;
}) {
  if (!result) {
    return (
      <p className="text-sm leading-relaxed text-slate-400">
        {emptyMessage}
      </p>
    );
  }

  if (result.blocked) {
    return (
      <div className="space-y-2">
        <p className="text-sm font-semibold text-amber-700">
          자동 실행이 제한되었습니다.
        </p>

        <p className="text-sm leading-relaxed text-slate-600">
          {result.block_reason ??
            "현재 자동 실행 검증 대상이 아닙니다."}
        </p>
      </div>
    );
  }

  if (result.timed_out) {
    return (
      <div className="space-y-2">
        <p className="text-sm font-semibold text-amber-700">
          실행 시간이 초과되었습니다.
        </p>

        {result.stdout && (
          <pre className="whitespace-pre-wrap break-words font-mono text-sm leading-relaxed text-slate-700">
            {result.stdout}
          </pre>
        )}
      </div>
    );
  }

  if (!result.success) {
    return (
      <div className="space-y-2">
        <p className="text-sm font-semibold text-red-700">
          코드가 정상적으로 종료되지 않았습니다.
        </p>

        {result.stderr && (
          <pre className="whitespace-pre-wrap break-words font-mono text-sm leading-relaxed text-red-700">
            {result.stderr}
          </pre>
        )}
      </div>
    );
  }

  if (!result.stdout) {
    return (
      <p className="text-sm leading-relaxed text-slate-500">
        정상적으로 실행되었으며 출력된 내용은 없습니다.
      </p>
    );
  }

  return (
    <pre className="whitespace-pre-wrap break-words font-mono text-sm leading-relaxed text-slate-800">
      {result.stdout}
    </pre>
  );
}

export default function StyleApplySection({
  selectedStyleId,
  setSelectedStyleId,
  savedStyles,
  selectedStyle,
  targetCode,
  setTargetCode,
  handleApplyStyle,
  styleApplyLoading,
  styleApplyResult,
  setStyleApplyResult,
  editableTransformedCode,
  setEditableTransformedCode,
}: StyleApplySectionProps) {
  const [useFunctionTests, setUseFunctionTests] =
    useState(false);


  const [functionDrafts, setFunctionDrafts] =
    useState<FunctionTestDraft[]>([
      createFunctionDraft(1),
    ]);

  const nextFunctionDraftId = useRef(2);

  const [
    functionInputError,
    setFunctionInputError,
  ] = useState("");

  const clearPreviousResult = () => {
    setStyleApplyResult(null);
    setEditableTransformedCode("");
  };

  const updateFunctionDraft = (
    id: number,
    field:
      | "functionName"
      | "argsText"
      | "kwargsText"
      | "stdinText",
    value: string
  ) => {
    setFunctionDrafts((current) =>
      current.map((draft) =>
        draft.id === id
          ? {
              ...draft,
              [field]: value,
            }
          : draft
      )
    );

    setFunctionInputError("");
    clearPreviousResult();
  };

  const addFunctionDraft = () => {
    if (
      functionDrafts.length >= MAX_FUNCTION_CASES
    ) {
      return;
    }

    const id = nextFunctionDraftId.current;
    nextFunctionDraftId.current += 1;

    setFunctionDrafts((current) => [
      ...current,
      createFunctionDraft(id),
    ]);

    setFunctionInputError("");
    clearPreviousResult();
  };

  const removeFunctionDraft = (id: number) => {
    setFunctionDrafts((current) => {
      if (current.length <= 1) {
        return current;
      }

      return current.filter(
        (draft) => draft.id !== id
      );
    });

    setFunctionInputError("");
    clearPreviousResult();
  };

  // CAPSTONE_STDIN_ONLY_INDEPENDENT_FUNCTION_CASES_V1:
  // An empty function name with stdin is a standalone stdin verification.
  // No function_cases are sent in this mode; the existing top-level stdin
  // reaches the execution verifier without changing backend contracts.
  const submitStyleApplication = () => {
    if (styleApplyLoading) {
      return;
    }

    if (!useFunctionTests) {
      setFunctionInputError("");
      void handleApplyStyle(undefined, false);
      return;
    }

    const selected = parseVerificationInputs(functionDrafts);
    if (!selected.ok) {
      setFunctionInputError(selected.error);
      return;
    }

    setFunctionInputError("");
    void handleApplyStyle(selected.functionCases, false, selected.stdin);
  };

  const missingSyntaxNames = new Set(
    styleApplyResult?.missingSyntaxTags.map(
      (item) => item.tag
    ) ?? []
  );

  const missingConceptNames = new Set(
    styleApplyResult?.missingConceptTags.map(
      (item) => item.tag
    ) ?? []
  );

  const appliedSyntaxTags =
    selectedStyle?.syntax_tags.filter(
      (item) => !missingSyntaxNames.has(item.tag)
    ) ?? [];

  const appliedConceptTags =
    selectedStyle?.concept_tags.filter(
      (item) => !missingConceptNames.has(item.tag)
    ) ?? [];

  const executionVerification =
    styleApplyResult?.applyResponse
      .execution_verification;

  const functionVerification =
    executionVerification?.function_verification;

  const editedAfterVerification =
    styleApplyResult !== null &&
    editableTransformedCode !==
      styleApplyResult.applyResponse
        .transformed_code;

  const transformationWasRejected =
    executionVerification?.status ===
    "different";

  return (
    <div className="space-y-6">
      {/* ========================================= */}
      {/* 스타일 적용 입력 영역 */}
      {/* ========================================= */}

      <section className="overflow-hidden rounded-2xl border border-slate-300 bg-white shadow-sm">
        <div className="border-b border-slate-200 px-6 py-5">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                Style Transformation
              </p>

              <h2 className="text-2xl font-bold text-slate-900">
                스타일 적용
              </h2>

              <p className="mt-2 text-sm leading-relaxed text-slate-600">
                저장된 코딩 스타일을 선택하고 다른 Python 코드에 적용합니다.
              </p>
            </div>

            <div className="self-start rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-600 lg:self-auto">
              Python Only
            </div>
          </div>
        </div>

        <div className="p-6">
          {/* ========================================= */}
          {/* Step 01: 저장 스타일 선택 */}
          {/* ========================================= */}

          <div className="mb-6">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                  Step 01
                </p>

                <h3 className="mt-1 text-base font-semibold text-slate-900">
                  적용할 코딩 스타일 선택
                </h3>
              </div>

              <span className="text-xs text-slate-400">
                {savedStyles.length}개 스타일
              </span>
            </div>

            <select
              value={selectedStyleId}
              onChange={(e) => {
                setSelectedStyleId(
                  e.target.value
                );
                clearPreviousResult();
              }}
              className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-500 focus:ring-2 focus:ring-slate-100"
            >
              <option value="">
                코딩 스타일을 선택하세요
              </option>

              {savedStyles.map((style) => (
                <option
                  key={style.id}
                  value={style.id}
                >
                  {style.name}
                </option>
              ))}
            </select>
          </div>

          {/* 선택한 스타일 상세 정보 */}

          {selectedStyle && (
            <div className="mb-6 rounded-2xl border border-slate-200 bg-slate-50 p-5">
              <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                    Selected Style
                  </p>

                  <h3 className="mt-1 text-lg font-bold text-slate-900">
                    {selectedStyle.name}
                  </h3>
                </div>

                {selectedStyle.is_shared && (
                  <span className="self-start rounded-full border border-green-200 bg-green-50 px-3 py-1 text-xs font-semibold text-green-700">
                    공유받은 스타일
                  </span>
                )}
              </div>

              <p className="text-sm leading-relaxed text-slate-600">
                {selectedStyle.description}
              </p>

              <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-2">
                <div>
                  <p className="mb-2 text-xs font-semibold text-blue-700">
                    문법 태그
                  </p>

                  <div className="flex flex-wrap gap-2">
                    {selectedStyle.syntax_tags.length ===
                    0 ? (
                      <span className="text-xs text-slate-400">
                        저장된 문법 태그가 없습니다.
                      </span>
                    ) : (
                      selectedStyle.syntax_tags.map(
                        (tag, idx) => (
                          <span
                            key={idx}
                            className="rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700"
                          >
                            {tag.tag}
                          </span>
                        )
                      )
                    )}
                  </div>
                </div>

                <div>
                  <p className="mb-2 text-xs font-semibold text-purple-700">
                    개념 태그
                  </p>

                  <div className="flex flex-wrap gap-2">
                    {selectedStyle.concept_tags.length ===
                    0 ? (
                      <span className="text-xs text-slate-400">
                        저장된 개념 태그가 없습니다.
                      </span>
                    ) : (
                      selectedStyle.concept_tags.map(
                        (tag, idx) => (
                          <span
                            key={idx}
                            className="rounded-full border border-purple-200 bg-purple-50 px-2.5 py-1 text-xs font-medium text-purple-700"
                          >
                            {tag.tag}
                          </span>
                        )
                      )
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ========================================= */}
          {/* Step 02: 코드 입력 */}
          {/* ========================================= */}

          <div>
            <div className="mb-3">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                Step 02
              </p>

              <h3 className="mt-1 text-base font-semibold text-slate-900">
                스타일을 적용할 코드 입력
              </h3>

              <p className="mt-1 text-sm text-slate-500">
                변환할 Python 코드를 입력해주세요.
              </p>
            </div>

            <CodeEditor
              code={targetCode}
              setCode={(value) => {
                setTargetCode(value);
                clearPreviousResult();
              }}
            />
          </div>

          {/* CAPSTONE_BATCH18_CASE_STDIN_ONLY_V1: stdin is provided inside each function test. */}
          {/* ========================================= */}
          {/* Step 03: 함수 반환값 검증 */}
          {/* ========================================= */}

          <div className="mt-6 rounded-2xl border border-slate-200 bg-slate-50 p-5">
            <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                  Step 03 · Optional
                </p>

                <h3 className="mt-1 text-base font-semibold text-slate-900">
                  표준 입력 및 함수 반환값 검증
                </h3>

                <p className="mt-2 text-sm leading-relaxed text-slate-600">
                  입력값만 작성하면 실행 출력을 비교하고,
                  함수 이름까지 입력하면 반환값도
                  함께 검증합니다.
                </p>
              </div>

              <label className="flex shrink-0 cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={useFunctionTests}
                  onChange={(e) => {
                    setUseFunctionTests(
                      e.target.checked
                    );
                    setFunctionInputError("");
                    clearPreviousResult();
                  }}
                  disabled={styleApplyLoading}
                  className="h-4 w-4 accent-slate-900"
                />

                <span className="text-sm font-semibold text-slate-800">
                  입력/함수 검증 사용
                </span>
              </label>
            </div>

            {!useFunctionTests ? (
              <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
                <p className="text-sm leading-relaxed text-slate-600">
                  함수 검증을 사용하지 않으면
                  기존처럼 코드의 실행 출력과
                  종료 상태만 비교합니다.
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                {/* 함수 테스트 사용 안내 */}

                <div className="rounded-xl border border-slate-200 bg-white p-4">
                  <p className="text-sm font-semibold text-slate-800">
                    함수 테스트 입력 방법
                  </p>

                  <p className="mt-2 text-sm leading-relaxed text-slate-600">
                    표준 입력만 검증할 때는 함수 이름을 비워 두고
                    사용자 입력값(stdin)만 입력하세요.
                    함수 반환값 검증 시에는 함수 이름과
                    함수에 넣을 값을 함께 입력해주세요.
                  </p>

                  <div className="mt-3 space-y-2 text-xs leading-relaxed text-slate-600">
                    <p>
                      <span className="font-semibold text-slate-800">
                        순서대로 넣을 값:
                      </span>{" "}
                      함수의 위치 인자를 왼쪽부터 순서대로 전달합니다.
                      리스트 한 개를 전달할 때는 [[1, 2, 3]]처럼 작성합니다.
                    </p>

                    <p>
                      <span className="font-semibold text-slate-800">
                        이름을 지정해 넣을 값:
                      </span>{" "}
                      함수에서 사용하는 이름을
                      직접 지정하여 값을 전달합니다.
                    </p>
                  </div>
                </div>

                {/* 여러 함수 테스트 입력 */}

                {functionDrafts.map(
                  (draft, index) => (
                    <div
                      key={draft.id}
                      className="rounded-xl border border-slate-200 bg-white p-4"
                    >
                      <div className="mb-4 flex items-center justify-between gap-3">
                        <h4 className="text-sm font-semibold text-slate-900">
                          함수 테스트 {index + 1}
                        </h4>

                        <button
                          type="button"
                          onClick={() =>
                            removeFunctionDraft(
                              draft.id
                            )
                          }
                          disabled={
                            styleApplyLoading ||
                            functionDrafts.length <=
                              1
                          }
                          className="text-xs font-medium text-red-600 hover:text-red-800 disabled:cursor-not-allowed disabled:text-slate-300"
                        >
                          삭제
                        </button>
                      </div>

                      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                        {/* 함수 이름 · CAPSTONE_BATCH25_CLEAR_NAME_PLACEHOLDER_V1 */}

                        <div>
                          <label
                            htmlFor={`function-name-${draft.id}`}
                            className="mb-2 block text-xs font-semibold text-slate-700"
                          >
                            함수 이름
                          </label>

                          <input
                            id={`function-name-${draft.id}`}
                            type="text"
                            value={
                              draft.functionName
                            }
                            onChange={(e) =>
                              updateFunctionDraft(
                                draft.id,
                                "functionName",
                                e.target.value
                              )
                            }
                            disabled={
                              styleApplyLoading
                            }
                            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 font-mono text-sm text-slate-800 outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-100"
                          />

                          <p className="mt-2 text-xs leading-relaxed text-slate-500">
                            함수 반환값 검증 시에만 입력합니다.
                            표준 입력만 검증할 때는 비워 두세요.
                          </p>
                        </div>

                        {/* 순서대로 넣을 값 */}

                        <div>
                          <label
                            htmlFor={`function-args-${draft.id}`}
                            className="mb-2 block text-xs font-semibold text-slate-700"
                          >
                            순서대로 넣을 값
                          </label>

                          <input
                            id={`function-args-${draft.id}`}
                            type="text"
                            value={draft.argsText}
                            onChange={(e) =>
                              updateFunctionDraft(
                                draft.id,
                                "argsText",
                                e.target.value
                              )
                            }
                            disabled={
                              styleApplyLoading
                            }
                            placeholder='["Jin"]'
                            spellCheck={false}
                            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 font-mono text-sm text-slate-800 outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-100"
                          />

                          <p className="mt-2 text-xs leading-relaxed text-slate-500">
                            예: [5] 또는
                            {" "}
                            [&quot;Jin&quot;]
                            {" "}
                            / 여러 값은 [5, 10]처럼
                            입력합니다. 타입 힌트나 기본값이 있는
                            매개변수는 해당 자료형과 일치해야 합니다.
                            사용하지 않으면 []로 두세요.
                          </p>
                        </div>

                        {/* 이름을 지정해 넣을 값 */}

                        <div className="lg:col-span-2">
                          <label
                            htmlFor={`function-kwargs-${draft.id}`}
                            className="mb-2 block text-xs font-semibold text-slate-700"
                          >
                            이름을 지정해 넣을 값
                            <span className="ml-2 font-normal text-slate-400">
                              (선택)
                            </span>
                          </label>

                          <input
                            id={`function-kwargs-${draft.id}`}
                            type="text"
                            value={
                              draft.kwargsText
                            }
                            onChange={(e) =>
                              updateFunctionDraft(
                                draft.id,
                                "kwargsText",
                                e.target.value
                              )
                            }
                            disabled={
                              styleApplyLoading
                            }
                            placeholder='{"punctuation": "?"}'
                            spellCheck={false}
                            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 font-mono text-sm text-slate-800 outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-100"
                          />

                          <p className="mt-2 text-xs leading-relaxed text-slate-500">
                            함수의 매개변수 이름을
                            지정하여 값을 전달합니다.
                            사용하지 않는 경우
                            {" "}
                            <code className="rounded bg-slate-100 px-1 font-mono font-semibold text-slate-700">
                              {"{}"}
                            </code>
                            {" "}
                            그대로 두시면 됩니다.
                          </p>

                        </div>

                        {/* 사용자 입력값: 이 함수 테스트에만 적용 · CAPSTONE_BATCH25_CLEAR_STDIN_PLACEHOLDER_V1 */}
                        <div className="lg:col-span-2">
                          <label htmlFor={`function-stdin-${draft.id}`}
                            className="mb-2 block text-xs font-semibold text-slate-700">
                            사용자 입력값 (stdin) <span className="font-normal text-slate-400">· 선택</span>
                          </label>
                          <textarea id={`function-stdin-${draft.id}`} rows={2} maxLength={8192}
                            value={draft.stdinText} disabled={styleApplyLoading}
                            onChange={(event) => updateFunctionDraft(draft.id, "stdinText", event.target.value)}
                            className="w-full resize-y rounded-lg border border-slate-300 bg-white p-3 font-mono text-sm text-slate-900"
                          />
                          <p className="mt-2 text-xs leading-relaxed text-slate-500">
                            {/* CAPSTONE_BATCH25_TYPE_NOTICE_V1 */}
                            각 입력값은 코드에서 요구하는 자료형에 맞아야 합니다.
                            input()은 문자열을 반환하며, int(input())는 정수로,
                            float(input())는 실수로 변환 가능한 값을 입력해야 합니다.
                            대괄호 없이 입력 순서대로 한 줄에 한 값씩 작성해주세요.
                            여러 테스트 중 첫 번째로 작성한 stdin을 기본 실행 비교에도 사용합니다.
                            함수별 입력은 해당 함수 테스트에서 각각 사용됩니다.
                          </p>
                        </div>

                      </div>
                    </div>
                  )
                )}

                {/* 테스트 추가 버튼 */}

                <div className="flex flex-wrap items-center justify-between gap-3">
                  <button
                    type="button"
                    onClick={addFunctionDraft}
                    disabled={
                      styleApplyLoading ||
                      functionDrafts.length >=
                        MAX_FUNCTION_CASES
                    }
                    className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    + 테스트 추가
                  </button>

                  <span className="text-xs text-slate-500">
                    {functionDrafts.length}
                    {" / "}
                    {MAX_FUNCTION_CASES}개
                  </span>
                </div>

                {/* 입력 오류 안내 */}

                {functionInputError && (
                  <p
                    role="alert"
                    className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700"
                  >
                    {functionInputError}
                  </p>
                )}

                <p className="text-xs leading-relaxed text-slate-500">
                  입력한 함수와 값은 실제 Python
                  코드에서 실행됩니다. 검증 결과는
                  입력한 값에 대해서만 확인되며,
                  현재 실행 환경은 완전한 보안
                  샌드박스가 아닙니다.
                  신뢰할 수 있는 코드만 사용해주세요.
                </p>
              </div>
            )}
          </div>

          {/* CAPSTONE_BATCH19_REMOVE_STRICT_UI_V1: optional strict checkbox removed. */}
          {/* 스타일 적용 버튼 */}

          <div className="mt-5 flex justify-end">
            <button
              type="button"
              onClick={submitStyleApplication}
              disabled={styleApplyLoading}
              className="inline-flex min-w-[180px] items-center justify-center whitespace-nowrap rounded-xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-400"
            >
              {styleApplyLoading
                ? "변환 중..."
                : "스타일 적용하기"}
            </button>
          </div>
        </div>
      </section>

      {/* ========================================= */}
      {/* 스타일 적용 결과 */}
      {/* ========================================= */}

      {styleApplyResult && (
        <section className="overflow-hidden rounded-2xl border border-slate-300 bg-white shadow-sm">
          <div className="border-b border-slate-200 px-6 py-5">
            <p className="mb-1 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
              Transformation Result
            </p>

            <div className="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <h2 className="text-2xl font-bold text-slate-900">
                  Before &amp; After
                </h2>

                <p className="mt-1 text-sm text-slate-500">
                  적용 스타일:{" "}
                  <span className="font-semibold text-slate-700">
                    {styleApplyResult.styleName}
                  </span>
                </p>
              </div>

              <p className="text-xs text-slate-400">
                변환 전 코드와 적용 후 코드를
                비교할 수 있습니다.
              </p>
            </div>
          </div>

          <div className="p-6">
            {/* 검증 이후 직접 수정된 경우 */}

            {editedAfterVerification && (
              <div className="mb-5 rounded-xl border border-amber-200 bg-amber-50 p-4">
                <p className="text-sm font-semibold text-amber-800">
                  검증 이후 코드가 수정되었습니다.
                </p>

                <p className="mt-1 text-sm leading-relaxed text-amber-800">
                  아래 실행 검증 결과는 서버에서
                  변환한 당시 코드에 대한 결과입니다.
                  직접 수정한 코드에는 적용되지
                  않으므로 다시 검증해야 합니다.
                </p>
              </div>
            )}

            {/* ========================================= */}
            {/* Before / After */}
            {/* ========================================= */}

            <div className="mb-6 grid grid-cols-1 gap-5 2xl:grid-cols-2">
              {/* 원본 코드 */}

              <div className="min-w-0">
                <div className="mb-3 flex items-center gap-2">
                  <span className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-100 text-xs font-bold text-slate-600">
                    A
                  </span>

                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                      Before
                    </p>

                    <p className="text-sm font-semibold text-slate-800">
                      변환 전 코드
                    </p>
                  </div>
                </div>

                <CodeViewer
                  title="Original Code"
                  code={
                    styleApplyResult.applyResponse
                      .original_code
                  }
                  readOnly={true}
                />

                <div className="mt-4 overflow-hidden rounded-xl border border-slate-200 bg-white">
                  <div className="border-b border-slate-200 bg-slate-50 px-4 py-3">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                      Execution Result
                    </p>

                    <p className="mt-0.5 text-sm font-semibold text-slate-800">
                      실행 결과
                    </p>
                  </div>

                  <div className="min-h-[110px] px-4 py-4">
                    <ExecutionOutput
                      result={
                        executionVerification?.original
                      }
                      emptyMessage="변환 전 코드의 실행 결과를 확인할 수 없습니다."
                    />
                  </div>
                </div>
              </div>

              {/* 변환 후 코드 */}

              <div className="min-w-0">
                <div className="mb-3 flex items-center gap-2">
                  <span className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white">
                    B
                  </span>

                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                      After
                    </p>

                    <p className="text-sm font-semibold text-slate-800">
                      스타일 적용 후 코드
                    </p>
                  </div>
                </div>

                <CodeViewer
                  title="Transformed Code"
                  code={editableTransformedCode}
                  readOnly={false}
                  onChange={
                    setEditableTransformedCode
                  }
                />

                <div className="mt-4 overflow-hidden rounded-xl border border-slate-200 bg-white">
                  <div className="border-b border-slate-200 bg-slate-50 px-4 py-3">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                      Execution Result
                    </p>

                    <p className="mt-0.5 text-sm font-semibold text-slate-800">
                      실행 결과
                    </p>
                  </div>

                  <div className="min-h-[110px] px-4 py-4">
                    <ExecutionOutput
                      result={
                        executionVerification?.transformed
                      }
                      emptyMessage="스타일 적용 후 코드의 실행 결과를 확인할 수 없습니다."
                    />
                  </div>
                </div>

                {transformationWasRejected && (
                  <p className="mt-2 text-xs leading-relaxed text-amber-700">
                    위 실행 결과는 원본 복원 전에
                    시도한 변환 코드의 결과입니다.
                    코드 편집기에는 복원된 원본이
                    표시됩니다.
                  </p>
                )}
              </div>
            </div>

            {/* ========================================= */}
            {/* 실행 검증 종합 결과 */}
            {/* ========================================= */}

            {executionVerification && (
              <div
                className={`mb-6 rounded-xl border p-4 ${getStatusClass(
                  executionVerification.status
                )}`}
              >
                <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                  <p className="text-sm font-semibold">
                    {executionVerification.status ===
                    "equivalent"
                      ? "변환 전·후 실행 결과 일치"
                      : executionVerification.status ===
                        "different"
                      ? "실행 결과 불일치 · 원본 코드 유지"
                      : "실행 결과 검증 불가"}
                  </p>

                  <span className="text-xs font-medium">
                    {executionVerification.source ===
                    "runtime+function_tests"
                      ? "Python 실행 + 함수 반환값 검증"
                      : "실제 Python 실행"}
                  </span>
                </div>

                <p className="mt-2 text-sm leading-relaxed">
                  {executionVerification.message}
                </p>
              </div>
            )}

            {/* ========================================= */}
            {/* 함수 반환값 검증 상세 결과 */}
            {/* ========================================= */}

            {functionVerification && (
              <FunctionReturnResults verification={functionVerification} />
            )}

            {/* CAPSTONE_STDIN_ONLY_HIDE_UNREQUESTED_FUNCTION_NOTICE_V1:
                No function name means only top-level stdin was verified. */}
            {!functionVerification &&
              useFunctionTests &&
              functionDrafts.some((draft) => draft.functionName.trim() !== "") &&
              styleApplyResult && (
              <div className="mb-6 rounded-xl border border-amber-200 bg-amber-50 p-4">
                <p className="text-sm font-semibold text-amber-800">
                  함수 테스트 결과를 확인할 수 없습니다.
                </p>
                <p className="mt-2 text-sm leading-relaxed text-amber-700">
                  {executionVerification?.message ||
                    "실행 정책 또는 코드 오류로 함수 테스트가 수행되지 않았습니다."}
                </p>
              </div>
            )}

            {/* ========================================= */}
            {/* 변환 상세 정보 */}
            {/* ========================================= */}

            <div className="border-t border-slate-200 pt-6">
              <div className="mb-4">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                  Transformation Details
                </p>

                <h3 className="mt-1 text-lg font-bold text-slate-900">
                  변환 정보
                </h3>
              </div>

              <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                {/* 적용 규칙 */}

                <div className="rounded-xl border border-green-200 bg-green-50 p-4">
                  <h4 className="mb-3 font-semibold text-green-800">
                    실제 적용된 변환 규칙
                  </h4>

                  {styleApplyResult.applyResponse
                    .applied_rules.length ===
                  0 ? (
                    <p className="text-sm leading-relaxed text-slate-600">
                      적용된 변환 규칙이 없습니다.
                    </p>
                  ) : (
                    <ul className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-slate-700">
                      {styleApplyResult.applyResponse.applied_rules.map(
                        (rule, idx) => (
                          <li key={idx}>
                            {rule}
                          </li>
                        )
                      )}
                    </ul>
                  )}
                </div>

                {/* 참고 사항 */}

                <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
                  <h4 className="mb-3 font-semibold text-amber-800">
                    참고 사항
                  </h4>

                  {styleApplyResult.applyResponse
                    .warnings.length ===
                  0 ? (
                    <p className="text-sm leading-relaxed text-slate-600">
                      별도의 참고 사항이 없습니다.
                    </p>
                  ) : (
                    <ul className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-slate-700">
                      {styleApplyResult.applyResponse.warnings.map(
                        (warning, idx) => (
                          <li key={idx}>
                            {warning}
                          </li>
                        )
                      )}
                    </ul>
                  )}
                </div>
              </div>

              {/* ========================================= */}
              {/* 최종 스타일 태그 분석 */}
              {/* ========================================= */}

              <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4">
                <div className="mb-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                    Final Style Analysis
                  </p>

                  <h4 className="mt-1 font-semibold text-slate-900">
                    실제 스타일 반영 결과
                  </h4>

                  <p className="mt-1 text-xs leading-relaxed text-slate-500">
                    스타일 적용 후 코드를 다시
                    분석하여 저장된 스타일 태그가
                    실제 코드에 반영되었는지
                    확인한 결과입니다.
                  </p>
                </div>

                <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                  {/* 적용 확인 */}

                  <div className="rounded-xl border border-green-200 bg-white p-4">
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <h5 className="font-semibold text-green-800">
                        적용 확인
                      </h5>

                      <span className="text-xs font-semibold text-green-700">
                        {appliedSyntaxTags.length +
                          appliedConceptTags.length}
                        개
                      </span>
                    </div>

                    {appliedSyntaxTags.length ===
                      0 &&
                    appliedConceptTags.length ===
                      0 ? (
                      <p className="text-sm leading-relaxed text-slate-500">
                        최종 코드에서 확인된 저장
                        스타일 태그가 없습니다.
                      </p>
                    ) : (
                      <div className="space-y-4">
                        {appliedSyntaxTags.length >
                          0 && (
                          <div>
                            <p className="mb-2 text-xs font-semibold text-slate-500">
                              문법 태그
                            </p>

                            <div className="flex flex-wrap gap-2">
                              {appliedSyntaxTags.map(
                                (tag, idx) => (
                                  <span
                                    key={`applied-syntax-${idx}`}
                                    className="rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700"
                                  >
                                    {tag.tag}
                                  </span>
                                )
                              )}
                            </div>
                          </div>
                        )}

                        {appliedConceptTags.length >
                          0 && (
                          <div>
                            <p className="mb-2 text-xs font-semibold text-slate-500">
                              개념 태그
                            </p>

                            <div className="flex flex-wrap gap-2">
                              {appliedConceptTags.map(
                                (tag, idx) => (
                                  <span
                                    key={`applied-concept-${idx}`}
                                    className="rounded-full border border-purple-200 bg-purple-50 px-2.5 py-1 text-xs font-medium text-purple-700"
                                  >
                                    {tag.tag}
                                  </span>
                                )
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  {/* 미적용 태그 */}

                  <div className="rounded-xl border border-amber-200 bg-white p-4">
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <h5 className="font-semibold text-amber-800">
                        미적용
                      </h5>

                      <span className="text-xs font-semibold text-amber-700">
                        {styleApplyResult.missingSyntaxTags.length +
                          styleApplyResult.missingConceptTags.length}
                        개
                      </span>
                    </div>

                    {styleApplyResult.missingSyntaxTags.length ===
                      0 &&
                    styleApplyResult.missingConceptTags.length ===
                      0 ? (
                      <p className="text-sm leading-relaxed text-slate-500">
                        저장 스타일의 모든 대상
                        태그가 최종 코드에서
                        확인되었습니다.
                      </p>
                    ) : (
                      <div className="space-y-4">
                        {styleApplyResult.missingSyntaxTags.length >
                          0 && (
                          <div>
                            <p className="mb-2 text-xs font-semibold text-slate-500">
                              문법 태그
                            </p>

                            <div className="flex flex-wrap gap-2">
                              {styleApplyResult.missingSyntaxTags.map(
                                (tag, idx) => (
                                  <span
                                    key={`missing-syntax-${idx}`}
                                    className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-800"
                                  >
                                    {tag.tag}
                                  </span>
                                )
                              )}
                            </div>
                          </div>
                        )}

                        {styleApplyResult.missingConceptTags.length >
                          0 && (
                          <div>
                            <p className="mb-2 text-xs font-semibold text-slate-500">
                              개념 태그
                            </p>

                            <div className="flex flex-wrap gap-2">
                              {styleApplyResult.missingConceptTags.map(
                                (tag, idx) => (
                                  <span
                                    key={`missing-concept-${idx}`}
                                    className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-800"
                                  >
                                    {tag.tag}
                                  </span>
                                )
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
