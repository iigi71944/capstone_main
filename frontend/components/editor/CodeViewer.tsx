"use client";

type Props = {
  title: string;
  code: string;
  readOnly?: boolean;
  onChange?: (value: string) => void;
};

export default function CodeViewer({
  title,
  code,
  readOnly = true,
  onChange,
}: Props) {
  return (
    <div className="rounded-xl border border-slate-300 bg-white p-4 shadow-sm min-w-0">
      <h3 className="text-base font-semibold text-slate-900 mb-3">{title}</h3>

      <textarea
        value={code}
        readOnly={readOnly}
        onChange={(e) => onChange?.(e.target.value)}
        spellCheck={false}
        className="w-full h-[420px] resize-none rounded-lg border border-slate-300 bg-slate-50 p-4 font-mono text-sm text-slate-900 overflow-auto whitespace-pre"
      />
    </div>
  );
}