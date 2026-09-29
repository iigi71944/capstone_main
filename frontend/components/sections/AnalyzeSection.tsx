import CodeEditor from "../editor/CodeEditor";
import { AnalysisResponse } from "../../types/analysis";

interface AnalyzeSectionProps {
  code: string;
  setCode: (value: string) => void;
  loading: boolean;
  handleAnalyze: () => void;
  result: AnalysisResponse | null;
  styleName: string;
  setStyleName: (value: string) => void;
  handleSaveStyle: () => void;
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
}: AnalyzeSectionProps) {
  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-slate-300 bg-white p-5 shadow-sm">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 mb-3">
          <div>
            <h2 className="text-2xl font-bold text-slate-900">코드 입력</h2>
            <p className="text-slate-600 mt-1">
              해당 영역에 분석할 코드를 입력해 주세요.
            </p>
          </div>

          <span className="self-start lg:self-auto rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-700 border border-slate-200">
            Python Only
          </span>
        </div>

        <CodeEditor code={code} setCode={setCode} />

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            onClick={handleAnalyze}
            disabled={loading}
            className="inline-flex items-center justify-center whitespace-nowrap min-w-[120px] px-5 py-2.5 rounded-lg bg-slate-900 text-white hover:bg-slate-700 disabled:bg-slate-400 transition"
          >
            {loading ? "분석 중..." : "분석하기"}
          </button>

          <span className="text-sm text-slate-600">
            분석 후 현재 결과를 코딩 스타일로 저장할 수 있습니다.
          </span>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-300 bg-white p-5 shadow-sm">
        <h2 className="text-2xl font-bold text-slate-900 mb-4">
          분석 결과
        </h2>

        {!result && (
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-slate-600">
            아직 분석 결과가 없습니다. 위 코드 입력창에 Python 코드를 작성한 뒤
            분석하기 버튼을 눌러 주세요.
          </div>
        )}

        {result && (
          <div className="space-y-6">
            {!result.success && (
              <div className="rounded-lg border border-red-300 bg-red-50 p-4">
                <h3 className="font-semibold text-red-700 mb-1">오류</h3>
                <p className="text-sm text-red-700">
                  {result.error || "알 수 없는 오류가 발생했습니다."}
                </p>
              </div>
            )}

            {result.success && (
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                <h3 className="font-semibold mb-2 text-slate-900">
                  현재 분석 결과를 코딩 스타일로 저장
                </h3>

                <p className="text-sm text-slate-600 mb-3">
                  추출된 문법 태그와 개념 태그의 집합을 하나의 코딩 스타일로
                  저장합니다.
                </p>

                <div className="flex flex-col sm:flex-row gap-3">
                  <input
                    type="text"
                    value={styleName}
                    onChange={(e) => setStyleName(e.target.value)}
                    placeholder="스타일 이름 입력"
                    className="flex-1 rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm outline-none focus:border-slate-500"
                  />

                  <button
                    onClick={handleSaveStyle}
                    className="whitespace-nowrap rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
                  >
                    스타일 저장
                  </button>
                </div>
              </div>
            )}

            {result.success && (
              <>
                <div>
                  <h3 className="font-semibold mb-2 text-slate-900">
                    문법 태그
                  </h3>

                  {result.syntax_tags.length === 0 ? (
                    <p className="text-sm text-slate-500">
                      문법 태그가 없습니다.
                    </p>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {result.syntax_tags.map((item, idx) => (
                        <span
                          key={idx}
                          className="px-3 py-1 rounded-full bg-blue-100 text-blue-800 text-sm font-medium"
                        >
                          {item.tag}
                          {item.count ? ` (${item.count})` : ""}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                <div>
                  <h3 className="font-semibold mb-2 text-slate-900">
                    개념 태그
                  </h3>

                  {result.concept_tags.length === 0 ? (
                    <p className="text-sm text-slate-500">
                      아직 개념 태그가 없습니다.
                    </p>
                  ) : (
                    <div className="space-y-3">
                      {result.concept_tags.map((item, idx) => (
                        <div
                          key={idx}
                          className="rounded-xl border border-purple-200 bg-purple-50 p-3"
                        >
                          <span className="inline-block px-3 py-1 rounded-full bg-purple-100 text-purple-800 text-sm font-medium mb-2">
                            {item.tag}
                          </span>

                          <p className="text-sm text-slate-700">
                            {"reason" in item && item.reason
                              ? item.reason
                              : `score: ${item.score ?? "-"}`}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div>
                  <h3 className="font-semibold mb-2 text-slate-900">
                    메트릭
                  </h3>

                  <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-3">
                    {Object.entries(result.metrics).map(([key, value]) => (
                      <div
                        key={key}
                        className="rounded-xl border border-slate-200 bg-slate-50 p-3"
                      >
                        <div className="text-lg font-bold text-slate-900">
                          {value}
                        </div>

                        <div className="text-xs text-slate-600 mt-1 break-words">
                          {key}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
        )}
      </section>
    </div>
  );
}