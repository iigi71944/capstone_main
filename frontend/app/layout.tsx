import "./globals.css";

export const metadata = {
  title: "나도 볼래(너의 코드)",
  description: "Python 코드 분석 및 개선 웹 서비스",
};

const workspaceMenuItems = [
  {
    href: "#analyze",
    number: "01",
    label: "코드 분석",
    description: "Python 코드의 구조와 특징 분석",
  },
  {
    href: "#style",
    number: "02",
    label: "스타일 목록",
    description: "저장한 코딩 스타일 관리",
  },
  {
    href: "#styleApply",
    number: "03",
    label: "스타일 적용",
    description: "저장한 스타일을 다른 코드에 적용",
  },
];

const libraryMenuItems = [
  {
    href: "#syntax",
    label: "문법 태그",
    description: "Python 문법 요소 확인",
  },
  {
    href: "#concept",
    label: "개념 태그",
    description: "코드의 구조적 특징 확인",
  },
];

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body className="min-h-screen bg-slate-100 text-slate-900">
        <main className="min-h-screen p-6 lg:p-8">
          <div className="mx-auto max-w-[1600px]">
            <div className="flex flex-col gap-6 lg:flex-row">
              <aside className="w-full self-start rounded-2xl border border-slate-300 bg-white p-4 shadow-sm lg:sticky lg:top-8 lg:w-64">
                <div className="border-b border-slate-200 px-2 pb-5 pt-1">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">
                    Code Style Analyzer
                  </p>

                  <h2 className="mt-1 text-lg font-bold text-slate-900">
                    나도 볼래
                  </h2>

                  
                </div>

                <nav className="mt-5">
                  <div>
                    <p className="mb-2 px-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400">
                      Workspace
                    </p>

                    <div className="space-y-2">
                      {workspaceMenuItems.map((item) => (
                        <a
                          key={item.href}
                          href={item.href}
                          className="group flex w-full items-start gap-3 rounded-xl border border-transparent px-3 py-3 transition hover:border-slate-200 hover:bg-slate-50"
                        >
                          <span className="mt-0.5 text-xs font-bold text-slate-400 transition group-hover:text-slate-700">
                            {item.number}
                          </span>

                          <span className="min-w-0">
                            <span className="block text-sm font-semibold text-slate-800">
                              {item.label}
                            </span>

                            <span className="mt-0.5 block text-[11px] leading-relaxed text-slate-400">
                              {item.description}
                            </span>
                          </span>
                        </a>
                      ))}
                    </div>
                  </div>

                  <div className="my-5 border-t border-slate-200" />

                  <div>
                    <p className="mb-2 px-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400">
                      Library
                    </p>

                    <div className="space-y-2">
                      {libraryMenuItems.map((item) => (
                        <a
                          key={item.href}
                          href={item.href}
                          className="group block rounded-xl border border-transparent px-3 py-3 transition hover:border-slate-200 hover:bg-slate-50"
                        >
                          <span className="block text-sm font-semibold text-slate-800">
                            {item.label}
                          </span>

                          <span className="mt-0.5 block text-[11px] leading-relaxed text-slate-400">
                            {item.description}
                          </span>
                        </a>
                      ))}
                    </div>
                  </div>

                  <div className="my-5 border-t border-slate-200" />

                  <div>
                    <p className="mb-2 px-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400">
                      Account
                    </p>

                    <a
                      href="#login"
                      className="group block rounded-xl border border-transparent px-3 py-3 transition hover:border-slate-200 hover:bg-slate-50"
                    >
                      <span className="block text-sm font-semibold text-slate-800">
                        로그인
                      </span>

                      <span className="mt-0.5 block text-[11px] leading-relaxed text-slate-400">
                        계정 및 저장 스타일 관리
                      </span>
                    </a>
                  </div>
                </nav>

                <div className="mt-6 rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                    Style Structure
                  </p>

                  <p className="text-xs leading-relaxed text-slate-500">
                    개념 태그는 코딩 스타일의 구조를 생성하고, 문법 태그는 코딩
                    스타일의 한계를 지정합니다.
                  </p>
                </div>
              </aside>

              <section className="min-w-0 flex-1">
                {children}
              </section>
            </div>
          </div>
        </main>
      </body>
    </html>
  );
}