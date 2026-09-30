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
  handleCopyText: (text: string, message: string) => void;
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
  handleCopyText,
}: StyleApplySectionProps) {
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

                <div className="mt-3 flex justify-end">
                  <button
                    onClick={() =>
                      handleCopyText(
                        editableTransformedCode,
                        "스타일 적용 코드가 복사되었습니다."
                      )
                    }
                    className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700"
                  >
                    적용 코드 복사
                  </button>
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

              <div className="mt-4 rounded-xl border border-dashed border-slate-300 bg-slate-50 px-4 py-3">
                <p className="text-xs leading-relaxed text-slate-500">
                  문법 태그와 개념 태그의 실제 적용 여부는 변환 후 재분석 기능을
                  보완한 뒤 이 영역에 표시할 예정입니다.
                </p>
              </div>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}