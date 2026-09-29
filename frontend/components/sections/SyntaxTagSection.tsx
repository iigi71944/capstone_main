interface SyntaxTagDoc {
  tag: string;
  desc: string;
}

interface SyntaxTagSectionProps {
  syntaxSearch: string;
  setSyntaxSearch: (value: string) => void;
  filteredSyntaxTags: SyntaxTagDoc[];
}

export default function SyntaxTagSection({
  syntaxSearch,
  setSyntaxSearch,
  filteredSyntaxTags,
}: SyntaxTagSectionProps) {
  return (
    <div className="bg-white border border-slate-300 rounded-2xl p-6 shadow-sm">
      <div className="mb-5">
        <h2 className="text-2xl font-semibold text-slate-900 mb-2">
          문법 태그 목록
        </h2>

        <input
          type="text"
          value={syntaxSearch}
          onChange={(e) => setSyntaxSearch(e.target.value)}
          placeholder="문법 태그 검색..."
          className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-800 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {filteredSyntaxTags.map((item, idx) => (
          <div
            key={idx}
            className="rounded-xl border border-blue-200 bg-blue-50 p-4"
          >
            <div className="inline-block px-3 py-1 rounded-full bg-blue-100 text-blue-800 text-sm font-semibold mb-2">
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