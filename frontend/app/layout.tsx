import "./globals.css";

export const metadata = {
  title: "나도 볼래(너의 코드)",
  description: "Python 코드 분석 및 개선 웹 서비스",
};

const menuItems = [
  { href: "#login", label: "로그인" },
  { href: "#style", label: "스타일 목록" },
  { href: "#styleApply", label: "스타일 적용" },
  { href: "#syntax", label: "문법 태그 목록" },
  { href: "#concept", label: "개념 태그 목록" },
  { href: "#analyze", label: "분석 화면" },
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
          <div className="max-w-[1600px] mx-auto">
            <div className="flex flex-col lg:flex-row gap-6">
              <aside className="lg:w-64 w-full bg-white border border-slate-300 rounded-2xl p-4 shadow-sm">
                <h2 className="text-lg font-semibold text-slate-900 mb-4">
                  메뉴
                </h2>

                <nav className="flex flex-col gap-3">
                  {menuItems.map((item) => (
                    <a
                      key={item.href}
                      href={item.href}
                      className="w-full text-left px-4 py-3 rounded-xl text-sm font-medium transition border bg-white text-slate-700 border-slate-200 hover:bg-slate-100"
                    >
                      {item.label}
                    </a>
                  ))}
                </nav>

                <div className="mt-6 rounded-xl bg-slate-50 border border-slate-200 p-4">
                  <p className="text-xs text-slate-500 leading-relaxed">
                    개념 태그는 코딩 스타일의 구조를 생성하고, 문법 태그는
                    코딩 스타일의 한계를 지정합니다.
                  </p>
                </div>
              </aside>

              <section className="flex-1 min-w-0">
                <div className="mb-6">
                  <h1 className="text-3xl font-bold mb-2 text-slate-900">
                    나도 볼래(너의 코드)
                  </h1>
                  <p className="text-slate-600 leading-relaxed">
                    Python 코드의 구조를 분석하고, 문법 태그·개념 태그·메트릭을
                    확인한 뒤 저장된 코딩 스타일을 다른 코드에 적용하는 웹
                    서비스입니다.
                  </p>
                </div>

                {children}
              </section>
            </div>
          </div>
        </main>
      </body>
    </html>
  );
}