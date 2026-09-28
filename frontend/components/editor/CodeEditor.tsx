"use client";

import Editor from "@monaco-editor/react";

interface CodeEditorProps {
  code: string;
  setCode: (value: string) => void;
}

export default function CodeEditor({
  code,
  setCode,
}: CodeEditorProps) {
  return (
    <div className="rounded-xl overflow-hidden border border-slate-300">
      <Editor
        height="720px"
        defaultLanguage="python"
        value={code}
        onChange={(value) => setCode(value ?? "")}
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