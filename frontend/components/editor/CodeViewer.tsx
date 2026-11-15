"use client";

// CAPSTONE_CODE_VIEWER_AUTOHEIGHT_V1
// Before/After only: expand to the full source height and soft-wrap long lines.
// This does not change the user's code, its line endings, or the editable After value.
import { useCallback, useEffect, useLayoutEffect, useRef } from "react";

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
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const resizeToContent = useCallback(() => {
    const field = textareaRef.current;
    if (!field) return;

    // Reset first: shrinking the text must also shrink the editor.
    // scrollHeight includes padding with border-box sizing; allow for its border.
    field.style.height = "auto";
    field.style.height = `${field.scrollHeight + 2}px`;
  }, []);

  // Runs before paint when the source changes, including direct After edits.
  useLayoutEffect(() => {
    resizeToContent();
  }, [code, resizeToContent]);

  useEffect(() => {
    const wrapper = textareaRef.current?.parentElement;
    if (!wrapper || typeof ResizeObserver === "undefined") return;

    // A change between one/two-column layout can change soft-wrap line count.
    // Ignore height-only changes to prevent a ResizeObserver feedback loop.
    let previousWidth = wrapper.getBoundingClientRect().width;
    const observer = new ResizeObserver(() => {
      const nextWidth = wrapper.getBoundingClientRect().width;
      if (Math.abs(nextWidth - previousWidth) > 0.5) {
        previousWidth = nextWidth;
        resizeToContent();
      }
    });
    observer.observe(wrapper);
    return () => observer.disconnect();
  }, [resizeToContent]);

  return (
    <div className="w-full max-w-full min-w-0 rounded-xl border border-slate-300 bg-white p-4 shadow-sm">
      <h3 className="mb-3 text-base font-semibold text-slate-900">{title}</h3>

      <textarea
        ref={textareaRef}
        aria-label={title}
        value={code}
        rows={1}
        wrap="soft"
        readOnly={readOnly}
        onChange={(e) => onChange?.(e.target.value)}
        spellCheck={false}
        className="block box-border w-full min-w-0 max-w-full min-h-[88px] resize-none overflow-hidden whitespace-pre-wrap break-words rounded-lg border border-slate-300 bg-slate-50 p-4 font-mono text-sm leading-6 text-slate-900"
        style={{ overflowWrap: "anywhere" }}
      />
    </div>
  );
}
