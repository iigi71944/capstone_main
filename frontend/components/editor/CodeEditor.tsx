"use client";

import { useEffect, useRef } from "react";
import Editor from "@monaco-editor/react";
import type { editor } from "monaco-editor";
import { buildDecorations, HighlightItem } from "../../lib/monacoDecorations";

interface CodeEditorProps {
  code: string;
  setCode: (value: string) => void;
  highlights: HighlightItem[];
}

export default function CodeEditor({
  code,
  setCode,
  highlights,
}: CodeEditorProps) {
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const monacoRef = useRef<typeof import("monaco-editor") | null>(null);
  const decorationIdsRef = useRef<string[]>([]);

  const applyDecorations = () => {
    if (!editorRef.current || !monacoRef.current) return;

    const decorations = buildDecorations(monacoRef.current, highlights || []);
    decorationIdsRef.current = editorRef.current.deltaDecorations(
      decorationIdsRef.current,
      decorations
    );
  };

  const handleEditorDidMount = (
    editorInstance: editor.IStandaloneCodeEditor,
    monaco: typeof import("monaco-editor")
  ) => {
    editorRef.current = editorInstance;
    monacoRef.current = monaco;
    applyDecorations();
  };

  useEffect(() => {
    applyDecorations();
  }, [highlights]);

  return (
    <div className="rounded-xl overflow-hidden border border-slate-300">
      <Editor
        height="720px"
        defaultLanguage="python"
        value={code}
        onChange={(value) => setCode(value ?? "")}
        onMount={handleEditorDidMount}
        theme="vs"
        options={{
          fontSize: 16,
          lineHeight: 27,
          minimap: { enabled: true },
          scrollBeyondLastLine: false,
          automaticLayout: true,
          tabSize: 4,
          insertSpaces: true,
          wordWrap: "off",
          padding: { top: 16, bottom: 16 },
          glyphMargin: true,
          lineNumbersMinChars: 4,
          lineDecorationsWidth: 18,
          folding: false,
          renderIndentGuides: true,
          guides: {
            indentation: true,
          },
          fontLigatures: false,
          scrollbar: {
            vertical: "visible",
            horizontal: "visible",
            useShadows: false,
            verticalScrollbarSize: 12,
            horizontalScrollbarSize: 12,
          },
        }}
      />
    </div>
  );
}