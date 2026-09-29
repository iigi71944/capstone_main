interface ConceptTagDoc {
  tag: string;
  desc: string;
}

interface ConceptTagSectionProps {
  conceptSearch: string;
  setConceptSearch: (value: string) => void;
  filteredConceptTags: ConceptTagDoc[];
}

export default function ConceptTagSection({
  conceptSearch,
  setConceptSearch,
  filteredConceptTags,
}: ConceptTagSectionProps) {
  return (
    <div className="bg-white border border-slate-300 rounded-2xl p-6 shadow-sm">
      <div className="mb-5">
        <h2 className="text-2xl font-semibold text-slate-900 mb-2">
          개념 태그 목록
        </h2>

        <input
          type="text"
          value={conceptSearch}
          onChange={(e) => setConceptSearch(e.target.value)}
          placeholder="개념 태그 검색..."
          className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-800 outline-none focus:border-purple-400 focus:ring-2 focus:ring-purple-100"
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {filteredConceptTags.map((item, idx) => (
          <div
            key={idx}
            className="rounded-xl border border-purple-200 bg-purple-50 p-4"
          >
            <div className="inline-block px-3 py-1 rounded-full bg-purple-100 text-purple-800 text-sm font-semibold mb-2">
              {item.tag}
            </div>

            <p className="text-sm text-slate-700 leading-relaxed">
              {item.desc}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}