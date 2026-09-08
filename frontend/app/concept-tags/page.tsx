const conceptTags = [
  { title: "함수 중심 구조", desc: "함수 정의가 여러 개 존재하고, 클래스 없이 함수 단위로 코드가 구성된 경우 부여됩니다." },
  { title: "클래스 중심 구조", desc: "클래스 정의가 포함되어 객체지향 방식의 구조를 가지는 경우 부여됩니다." },
  { title: "반복문 중심", desc: "for문 또는 while문 비중이 높아 반복 처리 로직이 중심인 경우 부여됩니다." },
  { title: "조건 분기 많음", desc: "if문 사용이 많아 조건에 따라 흐름이 자주 분기되는 경우 부여됩니다." },
  { title: "리스트 컴프리헨션 사용", desc: "리스트 컴프리헨션을 활용해 코드를 축약한 경우 부여됩니다." },
  { title: "중첩 깊이 높음", desc: "조건문, 반복문 등이 여러 단계로 중첩되어 있는 경우 부여됩니다." },
  { title: "절차형 스타일", desc: "함수나 클래스 없이 위에서 아래로 순차 실행되는 구조인 경우 부여됩니다." },
  { title: "모듈화된 코드", desc: "기능이 여러 함수로 분리되어 상대적으로 구조화된 경우 부여됩니다." },
  { title: "단순한 구조", desc: "전체 흐름이 비교적 짧고 단순하여 이해가 쉬운 구조인 경우 부여됩니다." },
  { title: "예외 처리 포함", desc: "오류 상황을 대비한 try-except 구문이 포함된 경우 부여됩니다." },
];

export default function ConceptTagsPage() {
  return (
    <div className="rounded-2xl border border-slate-300 bg-white p-6 shadow-sm">
      <h2 className="text-2xl font-bold text-slate-900">개념 태그 목록</h2>
      <p className="text-slate-600 mt-2 mb-6">
        현재 분석 엔진이 구조적 특징과 스타일 경향을 바탕으로 판단할 수 있는 개념 태그 목록입니다.
      </p>

      <input
        type="text"
        placeholder="개념 태그 검색..."
        className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 mb-6 text-slate-900 placeholder:text-slate-400 caret-slate-900 outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
      />

      <div className="grid grid-cols-1 2xl:grid-cols-2 gap-4">
        {conceptTags.map((tag) => (
          <div
            key={tag.title}
            className="rounded-2xl border border-purple-200 bg-purple-50 p-5"
          >
            <div className="inline-block rounded-full bg-purple-100 px-3 py-1 text-purple-800 text-sm font-semibold mb-3">
              {tag.title}
            </div>
            <p className="text-slate-700">{tag.desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}