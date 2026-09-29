import { CodingStyle } from "../../types/analysis";

interface AuthUser {
  email: string;
}

type SharedCodingStyle = CodingStyle & {
  is_shared?: boolean;
  shared_from?: string;
  shared_at?: string;
};

interface StyleSectionProps {
  currentUser: AuthUser | null;
  savedStyles: SharedCodingStyle[];
  shareModalStyle: SharedCodingStyle | null;
  shareTargetEmail: string;
  setShareTargetEmail: (value: string) => void;
  setShareModalStyle: (style: SharedCodingStyle | null) => void;
  handleOpenShareModal: (style: SharedCodingStyle) => void;
  handleDeleteStyle: (styleId: string) => void;
  handleShareStyle: () => void;
}

export default function StyleSection({
  currentUser,
  savedStyles,
  shareModalStyle,
  shareTargetEmail,
  setShareTargetEmail,
  setShareModalStyle,
  handleOpenShareModal,
  handleDeleteStyle,
  handleShareStyle,
}: StyleSectionProps) {
  return (
    <div className="bg-white border border-slate-300 rounded-2xl p-6 shadow-sm">
      <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-3 mb-5">
        <div>
          <h2 className="text-2xl font-semibold text-slate-900 mb-2">
            스타일 목록
          </h2>

          <p className="text-slate-600 leading-relaxed">
            분석 결과에서 저장한 코딩 스타일 목록입니다.
          </p>

          <p className="text-sm text-slate-500 mt-2">
            현재 계정: {currentUser ? currentUser.email : "비로그인 임시 저장소"}
          </p>
        </div>

        <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
          총 {savedStyles.length}개 스타일
        </div>
      </div>

      {savedStyles.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-5 text-sm text-slate-500">
          저장된 코딩 스타일이 없습니다.
        </div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 items-start">
          {savedStyles.map((style) => {
            const isShared = Boolean(style.is_shared);

            return (
              <div
                key={style.id}
                className={`rounded-xl border p-4 shadow-sm h-auto self-start ${
                  isShared
                    ? "border-green-300 bg-green-50"
                    : "border-slate-200 bg-slate-50"
                }`}
              >
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-semibold text-slate-900 break-words">
                        {style.name}
                      </h3>

                      {isShared && (
                        <span className="rounded-full bg-green-100 px-2.5 py-1 text-xs font-semibold text-green-800 border border-green-200">
                          공유받은 스타일
                        </span>
                      )}
                    </div>

                    <p className="text-xs text-slate-500 mt-1">
                      생성일: {style.created_at}
                    </p>

                    {isShared && style.shared_from && (
                      <p className="text-xs text-green-700 mt-1">
                        공유한 계정: {style.shared_from}
                      </p>
                    )}
                  </div>

                  <div className="flex shrink-0 gap-2">
                    <button
                      onClick={() => handleOpenShareModal(style)}
                      className="text-xs px-3 py-1 rounded-lg border border-blue-200 text-blue-700 bg-white hover:bg-blue-50"
                    >
                      공유
                    </button>

                    <button
                      onClick={() => handleDeleteStyle(style.id)}
                      className="text-xs px-3 py-1 rounded-lg border border-red-200 text-red-600 bg-white hover:bg-red-50"
                    >
                      삭제
                    </button>
                  </div>
                </div>

                <p className="text-sm text-slate-700 leading-relaxed mb-4 line-clamp-3">
                  {style.description}
                </p>

                <div className="mb-3">
                  <h4 className="text-sm font-semibold text-blue-800 mb-2">
                    문법 태그 한계
                  </h4>

                  {style.syntax_tags.length === 0 ? (
                    <p className="text-xs text-slate-500">
                      저장된 핵심 문법 태그가 없습니다.
                    </p>
                  ) : (
                    <div className="flex flex-wrap gap-2 max-h-24 overflow-y-auto pr-1">
                      {style.syntax_tags.map((tag, idx) => (
                        <span
                          key={idx}
                          className="px-2.5 py-1 rounded-full bg-blue-100 text-blue-800 text-xs font-medium"
                        >
                          {tag.tag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                <div>
                  <h4 className="text-sm font-semibold text-purple-800 mb-2">
                    개념 태그 구조
                  </h4>

                  {style.concept_tags.length === 0 ? (
                    <p className="text-xs text-slate-500">
                      저장된 개념 태그가 없습니다.
                    </p>
                  ) : (
                    <div className="flex flex-wrap gap-2 max-h-28 overflow-y-auto pr-1">
                      {style.concept_tags.map((tag, idx) => (
                        <span
                          key={idx}
                          className="px-2.5 py-1 rounded-full bg-purple-100 text-purple-800 text-xs font-medium"
                        >
                          {tag.tag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {shareModalStyle && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <div className="w-full max-w-md rounded-2xl bg-white border border-slate-300 p-5 shadow-xl">
            <h3 className="text-lg font-semibold text-slate-900 mb-2">
              코딩 스타일 공유
            </h3>

            <p className="text-sm text-slate-600 mb-4">
              공유할 계정의 이메일을 작성해주십시오.
            </p>

            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 mb-4">
              <p className="text-sm font-semibold text-slate-900">
                {shareModalStyle.name}
              </p>

              <p className="text-xs text-slate-500 mt-1">
                현재 공유 가능 계정: test001@gmail.com, test002@gmail.com
              </p>
            </div>

            <input
              type="email"
              value={shareTargetEmail}
              onChange={(e) => setShareTargetEmail(e.target.value)}
              placeholder="공유할 계정 이메일"
              className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none focus:border-slate-500 mb-4"
            />

            <div className="flex justify-end gap-2">
              <button
                onClick={() => {
                  setShareModalStyle(null);
                  setShareTargetEmail("");
                }}
                className="px-4 py-2 rounded-xl border border-slate-300 text-slate-700 hover:bg-slate-50"
              >
                취소
              </button>

              <button
                onClick={handleShareStyle}
                className="px-4 py-2 rounded-xl bg-slate-900 text-white hover:bg-slate-700"
              >
                공유하기
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}