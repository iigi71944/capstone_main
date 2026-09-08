const syntaxTags = [
  { title: "함수 정의", desc: "def로 정의된 함수가 있는지 분석합니다." },
  { title: "클래스 정의", desc: "class로 정의된 클래스가 있는지 분석합니다." },
  { title: "if문", desc: "조건 분기 로직이 포함되어 있는지 분석합니다." },
  { title: "for문", desc: "반복 처리에 for문이 사용되었는지 분석합니다." },
  { title: "while문", desc: "반복 처리에 while문이 사용되었는지 분석합니다." },
  { title: "return문", desc: "함수 내부 반환 구문 사용 여부를 분석합니다." },
  { title: "예외 처리", desc: "try-except 구문을 사용하는지 분석합니다." },
  { title: "리스트 컴프리헨션", desc: "리스트 컴프리헨션 문법 사용 여부를 분석합니다." },
  { title: "import문", desc: "모듈 또는 라이브러리 import 여부를 분석합니다." },
];

export default function SyntaxTagsPage() {
  return (
    <div className="rounded-2xl border border-slate-300 bg-white p-6 shadow-sm">
      <h2 className="text-2xl font-bold text-slate-900">문법 태그 목록</h2>
      <p className="text-slate-600 mt-2 mb-6">
        현재 분석 엔진이 인식할 수 있는 주요 Python 문법 태그 목록입니다.
      </p>

      <input
        type="text"
        placeholder="문법 태그 검색..."
        className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 mb-6 text-slate-900 placeholder:text-slate-400 caret-slate-900 outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
      />

      <div className="grid grid-cols-1 2xl:grid-cols-2 gap-4">
        {syntaxTags.map((tag) => (
          <div
            key={tag.title}
            className="rounded-2xl border border-blue-200 bg-blue-50 p-5"
          >
            <div className="inline-block rounded-full bg-blue-100 px-3 py-1 text-blue-800 text-sm font-semibold mb-3">
              {tag.title}
            </div>
            <p className="text-slate-700">{tag.desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}