"use client";

import CodeEditor from "../editor/CodeEditor";
import CodeViewer from "../editor/CodeViewer";

import type {
  AnalysisResponse,
  CodingStyle,
  ConceptTag,
  StyleApplyResponse,
  SyntaxTag,
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
  handleApplyStyle: () => void | Promise<void>;
  styleApplyLoading: boolean;
  styleApplyResult: StyleApplyResult | null;
  setStyleApplyResult: (value: StyleApplyResult | null) => void;
  editableTransformedCode: string;
  setEditableTransformedCode: (value: string) => void;
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
  const missingSyntaxNames = new Set(
    styleApplyResult?.missingSyntaxTags.map((item) => item.tag) ?? []
  );

  const missingConceptNames = new Set(
    styleApplyResult?.missingConceptTags.map((item) => item.tag) ?? []
  );

  const appliedSyntaxTags =
    selectedStyle?.syntax_tags.filter(
      (item) => !missingSyntaxNames.has(item.tag)
    ) ?? [];

  const appliedConceptTags =
    selectedStyle?.concept_tags.filter(
      (item) => !missingConceptNames.has(item.tag)
    ) ?? [];

  return (
    <div className="space-y-6">
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
                setSelectedStyleId(e.target.value);
                setStyleApplyResult(null);
                setEditableTransformedCode("");
              }}
              className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-500 focus:ring-2 focus:ring-slate-100"
            >
              <option value="">코딩 스타일을 선택하세요</option>

              {savedStyles.map((style) => (
                <option key={style.id} value={style.id}>
                  {style.name}
                </option>
              ))}
            </select>
          </div>

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
                    {selectedStyle.syntax_tags.length === 0 ? (
                      <span className="text-xs text-slate-400">
                        저장된 문법 태그가 없습니다.
                      </span>
                    ) : (
                      selectedStyle.syntax_tags.map((tag, idx) => (
                        <span
                          key={idx}
                          className="rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700"
                        >
                          {tag.tag}
                        </span>
                      ))
                    )}
                  </div>
                </div>

                <div>
                  <p className="mb-2 text-xs font-semibold text-purple-700">
                    개념 태그
                  </p>

                  <div className="flex flex-wrap gap-2">
                    {selectedStyle.concept_tags.length === 0 ? (
                      <span className="text-xs text-slate-400">
                        저장된 개념 태그가 없습니다.
                      </span>
                    ) : (
                      selectedStyle.concept_tags.map((tag, idx) => (
                        <span
                          key={idx}
                          className="rounded-full border border-purple-200 bg-purple-50 px-2.5 py-1 text-xs font-medium text-purple-700"
                        >
                          {tag.tag}
                        </span>
                      ))
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          <div>
            <div className="mb-3">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                Step 02
              </p>

              <h3 className="mt-1 text-base font-semibold text-slate-900">
                스타일을 적용할 코드 입력
              </h3>

              <p className="mt-1 text-sm text-slate-500">
                변환할 Python 코드를 입력한 뒤 스타일 적용을 실행해 주세요.
              </p>
            </div>

            <CodeEditor code={targetCode} setCode={setTargetCode} />
          </div>

          <div className="mt-5 flex justify-end">
            <button
              onClick={handleApplyStyle}
              disabled={styleApplyLoading}
              className="inline-flex min-w-[180px] items-center justify-center whitespace-nowrap rounded-xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-400"
            >
              {styleApplyLoading ? "변환 중..." : "스타일 적용하기"}
            </button>
          </div>
        </div>
      </section>

      {styleApplyResult && (
        <section className="overflow-hidden rounded-2xl border border-slate-300 bg-white shadow-sm">
          <div className="border-b border-slate-200 px-6 py-5">
            <p className="mb-1 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
              Transformation Result
            </p>

            <div className="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <h2 className="text-2xl font-bold text-slate-900">
                  Before & After
                </h2>

                <p className="mt-1 text-sm text-slate-500">
                  적용 스타일:{" "}
                  <span className="font-semibold text-slate-700">
                    {styleApplyResult.styleName}
                  </span>
                </p>
              </div>

              <p className="text-xs text-slate-400">
                변환 전 코드와 적용 후 코드를 비교할 수 있습니다.
              </p>
            </div>
          </div>

          <div className="p-6">
            <div className="mb-6 grid grid-cols-1 gap-5 2xl:grid-cols-2">
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
                  code={styleApplyResult.applyResponse.original_code}
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
                    <p className="text-sm leading-relaxed text-slate-400">
                      변환 전 코드의 실행 결과가 표시됩니다.
                    </p>
                  </div>
                </div>
              </div>

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
                  onChange={setEditableTransformedCode}
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
                    <p className="text-sm leading-relaxed text-slate-400">
                      스타일 적용 후 코드의 실행 결과가 표시됩니다.
                    </p>
                  </div>
                </div>
              </div>
            </div>

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
                <div className="rounded-xl border border-green-200 bg-green-50 p-4">
                  <h4 className="mb-3 font-semibold text-green-800">
                    실제 적용된 변환 규칙
                  </h4>

                  {styleApplyResult.applyResponse.applied_rules.length === 0 ? (
                    <p className="text-sm leading-relaxed text-slate-600">
                      적용된 변환 규칙이 없습니다.
                    </p>
                  ) : (
                    <ul className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-slate-700">
                      {styleApplyResult.applyResponse.applied_rules.map(
                        (rule, idx) => (
                          <li key={idx}>{rule}</li>
                        )
                      )}
                    </ul>
                  )}
                </div>

                <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
                  <h4 className="mb-3 font-semibold text-amber-800">
                    참고 사항
                  </h4>

                  {styleApplyResult.applyResponse.warnings.length === 0 ? (
                    <p className="text-sm leading-relaxed text-slate-600">
                      별도의 참고 사항이 없습니다.
                    </p>
                  ) : (
                    <ul className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-slate-700">
                      {styleApplyResult.applyResponse.warnings.map(
                        (warning, idx) => (
                          <li key={idx}>{warning}</li>
                        )
                      )}
                    </ul>
                  )}
                </div>
              </div>

              <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4">
                <div className="mb-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                    Final Style Analysis
                  </p>

                  <h4 className="mt-1 font-semibold text-slate-900">
                    실제 스타일 반영 결과
                  </h4>

                  <p className="mt-1 text-xs leading-relaxed text-slate-500">
                    스타일 적용 후 코드를 다시 분석하여 저장된 스타일 태그가
                    실제 코드에 반영되었는지 확인한 결과입니다.
                  </p>
                </div>

                <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
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

                    {appliedSyntaxTags.length === 0 &&
                    appliedConceptTags.length === 0 ? (
                      <p className="text-sm leading-relaxed text-slate-500">
                        최종 코드에서 확인된 저장 스타일 태그가 없습니다.
                      </p>
                    ) : (
                      <div className="space-y-4">
                        {appliedSyntaxTags.length > 0 && (
                          <div>
                            <p className="mb-2 text-xs font-semibold text-slate-500">
                              문법 태그
                            </p>

                            <div className="flex flex-wrap gap-2">
                              {appliedSyntaxTags.map((tag, idx) => (
                                <span
                                  key={`applied-syntax-${idx}`}
                                  className="rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700"
                                >
                                  {tag.tag}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}

                        {appliedConceptTags.length > 0 && (
                          <div>
                            <p className="mb-2 text-xs font-semibold text-slate-500">
                              개념 태그
                            </p>

                            <div className="flex flex-wrap gap-2">
                              {appliedConceptTags.map((tag, idx) => (
                                <span
                                  key={`applied-concept-${idx}`}
                                  className="rounded-full border border-purple-200 bg-purple-50 px-2.5 py-1 text-xs font-medium text-purple-700"
                                >
                                  {tag.tag}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>

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

                    {styleApplyResult.missingSyntaxTags.length === 0 &&
                    styleApplyResult.missingConceptTags.length === 0 ? (
                      <p className="text-sm leading-relaxed text-slate-500">
                        저장 스타일의 모든 대상 태그가 최종 코드에서
                        확인되었습니다.
                      </p>
                    ) : (
                      <div className="space-y-4">
                        {styleApplyResult.missingSyntaxTags.length > 0 && (
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

                        {styleApplyResult.missingConceptTags.length > 0 && (
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