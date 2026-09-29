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
      <section className="bg-white border border-slate-300 rounded-2xl p-6 shadow-sm">
        <h2 className="text-2xl font-semibold text-slate-900 mb-2">
          스타일 적용
        </h2>

        <p className="text-slate-600 mb-5 leading-relaxed">
          저장된 코딩 스타일을 선택하고, 다른 코드에 실제 변환을 적용합니다.
        </p>

        <div className="mb-5">
          <label className="block text-sm font-semibold text-slate-800 mb-2">
            적용할 코딩 스타일 선택
          </label>

          <select
            value={selectedStyleId}
            onChange={(e) => {
              setSelectedStyleId(e.target.value);
              setStyleApplyResult(null);
              setEditableTransformedCode("");
            }}
            className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none focus:border-slate-500"
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
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 mb-5">
            <h3 className="font-semibold text-slate-900 mb-2">
              선택된 스타일 설명
            </h3>

            <p className="text-sm text-slate-700 leading-relaxed">
              {selectedStyle.description}
            </p>
          </div>
        )}

        <div>
          <h3 className="font-semibold text-slate-900 mb-3">
            스타일을 적용할 코드 입력
          </h3>

          <CodeEditor code={targetCode} setCode={setTargetCode} />
        </div>

        <div className="mt-4">
          <button
            onClick={handleApplyStyle}
            disabled={styleApplyLoading}
            className="inline-flex items-center justify-center whitespace-nowrap min-w-[160px] px-5 py-2.5 rounded-xl bg-slate-900 text-white hover:bg-slate-700 disabled:bg-slate-400 transitionfont-medium"
          >
            {styleApplyLoading ? "변환 중..." : "스타일 실제 적용"}
          </button>
        </div>
      </section>

      {styleApplyResult && (
        <section className="bg-white border border-slate-300 rounded-2xl p-6 shadow-sm">
          <h2 className="text-xl font-semibold text-slate-900 mb-4">
            스타일 적용 결과
          </h2>

          <div className="grid grid-cols-1 2xl:grid-cols-2 gap-4 mb-5">
            <CodeViewer
              title="변환 전 코드"
              code={styleApplyResult.applyResponse.original_code}
              readOnly={true}
            />

            <div>
              <CodeViewer
                title="스타일 적용 후 코드"
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
                  className="px-4 py-2 rounded-lg bg-slate-900 text-white hover:bg-slate-700 transition"
                >
                  적용 코드 복사
                </button>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-5">
            <div className="rounded-xl border border-blue-200 bg-blue-50 p-4">
              <h3 className="font-semibold text-blue-800 mb-2">
                적용되지 않은 문법 태그
              </h3>

              {styleApplyResult.missingSyntaxTags.length === 0 ? (
                <p className="text-sm text-slate-600">
                  저장된 스타일의 문법 태그가 대상 코드에 대부분 반영되어
                  있습니다.
                </p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {styleApplyResult.missingSyntaxTags.map((tag, idx) => (
                    <span
                      key={idx}
                      className="px-3 py-1 rounded-full bg-blue-100 text-blue-800 text-sm font-medium"
                    >
                      {tag.tag}
                    </span>
                  ))}
                </div>
              )}
            </div>

            <div className="rounded-xl border border-purple-200 bg-purple-50 p-4">
              <h3 className="font-semibold text-purple-800 mb-2">
                적용되지 않은 개념 태그
              </h3>

              {styleApplyResult.missingConceptTags.length === 0 ? (
                <p className="text-sm text-slate-600">
                  저장된 스타일의 구조적 특징이 대상 코드에 대부분 반영되어
                  있습니다.
                </p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {styleApplyResult.missingConceptTags.map((tag, idx) => (
                    <span
                      key={idx}
                      className="px-3 py-1 rounded-full bg-purple-100 text-purple-800 text-sm font-medium"
                    >
                      {tag.tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>

          {styleApplyResult.applyResponse.applied_rules.length > 0 && (
            <div className="rounded-xl border border-green-200 bg-green-50 p-4 mb-5">
              <h3 className="font-semibold text-green-800 mb-2">
                실제 적용된 변환 규칙
              </h3>

              <ul className="list-disc pl-5 text-sm text-slate-700 space-y-1">
                {styleApplyResult.applyResponse.applied_rules.map(
                  (rule, idx) => (
                    <li key={idx}>{rule}</li>
                  )
                )}
              </ul>
            </div>
          )}

          {styleApplyResult.applyResponse.warnings.length > 0 && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
              <h3 className="font-semibold text-amber-800 mb-2">
                참고 사항
              </h3>

              <ul className="list-disc pl-5 text-sm text-slate-700 space-y-1">
                {styleApplyResult.applyResponse.warnings.map(
                  (warning, idx) => (
                    <li key={idx}>{warning}</li>
                  )
                )}
              </ul>
            </div>
          )}
        </section>
      )}
    </div>
  );
}