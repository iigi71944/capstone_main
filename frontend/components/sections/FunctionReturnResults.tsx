"use client";

import type {
  FunctionVerification,
  FunctionResultRecord,
  VerificationStatus,
} from "../../types/analysis";

interface FunctionReturnResultsProps {
  verification: FunctionVerification;
}

type EncodedValue = {
  type?: unknown;
  value?: unknown;
  items?: unknown;
};

function getStatusLabel(status: VerificationStatus): string {
  if (status === "equivalent") return "일치";
  if (status === "different") return "불일치";
  return "검증 불가";
}

function getStatusClass(status: VerificationStatus): string {
  if (status === "equivalent") {
    return "border-green-200 bg-green-50 text-green-800";
  }
  if (status === "different") {
    return "border-red-200 bg-red-50 text-red-800";
  }
  return "border-amber-200 bg-amber-50 text-amber-800";
}

function formatEncodedValue(encoded: unknown, depth = 0): string {
  if (depth > 7) return "(깊이 제한)";
  if (!encoded || typeof encoded !== "object") {
    return JSON.stringify(encoded) ?? "알 수 없음";
  }

  const value = encoded as EncodedValue;

  if (value.type === "NoneType") return "None";
  if (value.type === "bool") {
    return value.value === true ? "True" : "False";
  }
  if (value.type === "str") {
    return JSON.stringify(value.value) ?? '""';
  }
  if (value.type === "int" || value.type === "float") {
    return String(value.value);
  }
  if (value.type === "list" || value.type === "tuple") {
    const items = Array.isArray(value.items) ? value.items : [];
    const text = items.map((item) => formatEncodedValue(item, depth + 1));
    if (value.type === "list") return `[${text.join(", ")}]`;
    return `(${text.join(", ")}${text.length === 1 ? "," : ""})`;
  }
  if (value.type === "dict") {
    const items = value.items;
    if (!items || typeof items !== "object" || Array.isArray(items)) {
      return "{}";
    }
    const pairs = Object.entries(items).map(
      ([key, item]) => `${JSON.stringify(key)}: ${formatEncodedValue(item, depth + 1)}`
    );
    return `{${pairs.join(", ")}}`;
  }

  return JSON.stringify(encoded, null, 2) ?? "알 수 없음";
}

function describeResult(result: FunctionResultRecord | null | undefined): {
  title: string;
  value: string;
  typeLabel: string;
} {
  if (!result) {
    return {
      title: "반환값 확인 불가",
      value: "실행 차단, 시간 초과, 실행 오류 또는 결과 누락으로 값을 확인하지 못했습니다.",
      typeLabel: "확인 불가",
    };
  }

  if (result.kind === "exception") {
    return {
      title: "함수 실행 중 예외 발생",
      value: `${result.type ?? "Exception"}: ${result.message ?? ""}`,
      typeLabel: "예외",
    };
  }

  if (result.kind === "unsupported") {
    return {
      title: "지원되지 않는 반환 자료형",
      value: result.reason ?? "현재 검증할 수 없는 반환값입니다.",
      typeLabel: "검증 불가",
    };
  }

  if (result.kind === "value") {
    const encoded = result.value;
    const typeLabel = (
      encoded &&
      typeof encoded === "object" &&
      "type" in encoded &&
      typeof encoded.type === "string"
    ) ? encoded.type : "알 수 없음";

    return {
      title: "실제 반환값",
      value: formatEncodedValue(encoded),
      typeLabel,
    };
  }

  return {
    title: "반환값 확인 불가",
    value: "알 수 없는 응답 형식입니다.",
    typeLabel: "확인 불가",
  };
}

function ResultPanel({
  label,
  result,
  stdout,
}: {
  label: string;
  result?: FunctionResultRecord | null;
  stdout?: string | null;
}) {
  const detail = describeResult(result);

  return (
    <div className="min-w-0 rounded-xl border border-slate-200 bg-slate-50 p-4">
      <p className="text-sm font-semibold text-slate-900">{label}</p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="text-xs text-slate-500">{detail.title}</span>
        <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5 font-mono text-xs text-slate-600">
          {detail.typeLabel}
        </span>
      </div>
      <pre className="mt-2 w-full whitespace-pre-wrap break-words [overflow-wrap:anywhere] rounded-lg bg-white p-3 font-mono text-sm leading-6 text-slate-800">
        {detail.value}
      </pre>
      {stdout ? (
        <div className="mt-3">
          <p className="mb-1 text-xs font-medium text-slate-600">테스트 실행 중 출력(print)</p>
          <pre className="whitespace-pre-wrap break-words [overflow-wrap:anywhere] rounded-lg bg-white p-3 font-mono text-xs text-slate-700">
            {stdout}
          </pre>
        </div>
      ) : null}
    </div>
  );
}

export default function FunctionReturnResults({
  verification,
}: FunctionReturnResultsProps) {
  return (
    <section className="mb-6 overflow-hidden rounded-xl border border-slate-200 bg-white">
      <div className="border-b border-slate-200 bg-slate-50 px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-base font-bold text-slate-900">함수 반환값 검증 결과</h3>
          <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${getStatusClass(verification.status)}`}>
            {getStatusLabel(verification.status)}
          </span>
        </div>
        <p className="mt-2 text-sm leading-relaxed text-slate-600">
          입력하신 값으로 함수를 호출한 뒤, 변환 전·후 실제 반환값과 자료형을 비교했습니다.
        </p>
      </div>

      <div className="space-y-5 p-5">
        {verification.cases.map((testCase, index) => (
          <div key={`${testCase.function}-${index}`} className="rounded-xl border border-slate-200 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs text-slate-500">함수 테스트 {index + 1}</p>
                <p className="mt-1 font-mono text-sm font-semibold text-slate-900">
                  {testCase.function}()
                </p>
              </div>
              <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${getStatusClass(testCase.status)}`}>
                {getStatusLabel(testCase.status)}
              </span>
            </div>

            <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
              <div>
                <p className="mb-1 text-xs font-semibold text-slate-600">순서대로 넣은 값</p>
                <pre className="whitespace-pre-wrap break-words [overflow-wrap:anywhere] rounded-lg bg-slate-50 p-3 font-mono text-xs">
                  {JSON.stringify(testCase.args, null, 2)}
                </pre>
              </div>
              <div>
                <p className="mb-1 text-xs font-semibold text-slate-600">이름을 지정해 넣은 값</p>
                <pre className="whitespace-pre-wrap break-words [overflow-wrap:anywhere] rounded-lg bg-slate-50 p-3 font-mono text-xs">
                  {JSON.stringify(testCase.kwargs, null, 2)}
                </pre>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
              <ResultPanel
                label="스타일 적용 전 반환값"
                result={testCase.original_result}
                stdout={testCase.original_stdout}
              />
              <ResultPanel
                label="스타일 적용 후 반환값"
                result={testCase.transformed_result}
                stdout={testCase.transformed_stdout}
              />
            </div>

            <p className="mt-3 text-sm leading-relaxed text-slate-600">{testCase.message}</p>
          </div>
        ))}
        <p className="text-xs leading-relaxed text-slate-500">
          반환값 일치는 입력한 테스트 사례에 대한 결과입니다. 모든 입력이나 부작용의 동일성을 증명하지는 않습니다.
          반환값과 함수 내부 print 출력은 서로 다른 항목으로 표시됩니다.
        </p>
      </div>
    </section>
  );
}
