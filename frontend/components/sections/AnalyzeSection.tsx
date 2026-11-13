
import CodeEditor from "../editor/CodeEditor";

import type {
  AnalysisResponse,
  CodingStyle,
} from "../../types/analysis";

interface AnalyzeSectionProps {
  code: string;
  setCode: (value: string) => void;
  loading: boolean;
  handleAnalyze: () => void;
  result: AnalysisResponse | null;
  styleName: string;
  setStyleName: (value: string) => void;
  handleSaveStyle: () => void;

  // 실제 저장할 객체와 동일한 데이터입니다.
  stylePreview: CodingStyle | null;
}

export default function AnalyzeSection({
  code,
  setCode,
  loading,
  handleAnalyze,
  result,
  styleName,
  setStyleName,
  handleSaveStyle,
  stylePreview,
}: AnalyzeSectionProps) {
  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-slate-300 bg-white p-5 shadow-sm">
        <div className="mb-3 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h2 className="text-2xl font-bold text-slate-900">
              코드 입력
            </h2>

            <p className="mt-1 text-slate-600">
              해당 영역에 분석할 코드를 입력해 주세요.
            </p>
          </div>

          <span className="self-start rounded-full border border-slate-200 bg-slate-100 px-3 py-1 text-sm text-slate-700 lg:self-auto">
            Python Only
          </span>
        </div>

        <CodeEditor
          code={code}
          setCode={setCode}
        />

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={handleAnalyze}
            disabled={loading}
            className="inline-flex min-w-[120px] items-center justify-center whitespace-nowrap rounded-lg bg-slate-900 px-5 py-2.5 text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-400"
          >
            {loading ? "분석 중..." : "분석하기"}
          </button>

          <span className="text-sm text-slate-600">
            분석 후 현재 결과를 코딩 스타일로 저장할 수 있습니다.
          </span>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-300 bg-white p-5 shadow-sm">
        <h2 className="mb-4 text-2xl font-bold text-slate-900">
          분석 결과
        </h2>

        {!result && (
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <p className="text-sm leading-relaxed text-slate-600">
              아직 분석 결과가 없습니다.
              위 코드 입력창에 Python 코드를 작성한 뒤
              분석하기 버튼을 눌러 주세요.
            </p>
          </div>
        )}

        {result && !result.success && (
          <div className="rounded-xl border border-red-300 bg-red-50 p-4">
            <h3 className="mb-2 font-semibold text-red-700">
              분석 오류
            </h3>

            <p className="text-sm leading-relaxed text-red-700">
              {result.error ||
                "코드를 분석하는 중 오류가 발생했습니다."}
            </p>
          </div>
        )}

        {result?.success && (
          <div className="space-y-5">
            <div className="flex items-start gap-3 rounded-xl border border-green-200 bg-green-50 p-4">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-green-600 text-sm font-bold text-white">
                ✓
              </span>

              <div>
                <h3 className="font-semibold text-green-800">
                  코드 분석이 완료되었습니다.
                </h3>

                <p className="mt-1 text-sm leading-relaxed text-green-800">
                  분석된 문법 태그와 개념 태그를
                  바탕으로 코딩 스타일을 저장할 수 있습니다.
                </p>
              </div>
            </div>

            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <h3 className="mb-2 font-semibold text-slate-900">
                현재 분석 결과를 코딩 스타일로 저장
              </h3>

              <p className="mb-3 text-sm leading-relaxed text-slate-600">
                분석된 코딩 스타일에 이름을 지정하여
                저장합니다. 저장한 스타일은 스타일 목록에서
                확인하고 다른 Python 코드에 적용할 수 있습니다.
              </p>

              <div className="flex flex-col gap-3 sm:flex-row">
                <input
                  type="text"
                  value={styleName}
                  onChange={(e) =>
                    setStyleName(e.target.value)
                  }
                  placeholder="스타일 이름 입력"
                  className="min-w-0 flex-1 rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm outline-none transition focus:border-slate-500 focus:ring-2 focus:ring-slate-100"
                />

                <button
                  type="button"
                  onClick={handleSaveStyle}
                  className="whitespace-nowrap rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700"
                >
                  스타일 저장
                </button>
              </div>

              {/* 실제 저장되는 데이터 미리보기 */}
              {stylePreview && (
                <div className="mt-5 min-w-0 rounded-xl border border-slate-200 bg-white p-4">
                  <h3 className="text-base font-bold text-slate-900">
                    실제 저장되는 원본 코딩 스타일
                  </h3>

                  <p className="mt-2 text-sm leading-relaxed text-slate-600">
                    스타일 저장 버튼을 누르면 아래 JSON
                    객체가 브라우저 저장소에 저장됩니다.
                    스타일 이름을 변경하면 JSON의 이름도
                    함께 변경됩니다.
                  </p>

                  <pre
                    aria-label="실제 저장되는 원본 코딩 스타일 JSON"
                    className="mt-4 w-full whitespace-pre-wrap break-words [overflow-wrap:anywhere] rounded-xl border border-slate-200 bg-slate-50 p-4 font-mono text-xs leading-6 text-slate-800"
                  >
                    {JSON.stringify(stylePreview, null, 2)}
                  </pre>

                  <p className="mt-3 text-xs leading-relaxed text-slate-500">
                    JSON의 모든 항목을 표시합니다.
                    데이터가 길어지면 영역 높이가 자동으로
                    늘어나며, 내부 세로 스크롤은 사용하지 않습니다.
                    원본 Python 코드 자체는 저장하지 않습니다.
                  </p>
                </div>
              )}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
