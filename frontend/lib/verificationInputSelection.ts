/**
 * Frontend-only input routing for style application.
 * An unnamed test row containing only stdin is NOT a function test.
 * Send its stdin through the existing top-level `stdin` API property.
 * No new UI controls, backend routes, or payload fields are required.
 */
import type { FunctionTestCase } from "../types/analysis";

export interface VerificationInputDraft {
  functionName: string;
  argsText: string;
  kwargsText: string;
  stdinText: string;
}

export type VerificationInputSelection =
  | { ok: true; functionCases: FunctionTestCase[] | undefined; stdin: string | undefined }
  | { ok: false; error: string };

const fail = (error: string): VerificationInputSelection => ({ ok: false, error });

export function parseVerificationInputs(
  drafts: readonly VerificationInputDraft[]
): VerificationInputSelection {
  const functionCases: FunctionTestCase[] = [];
  let stdin: string | undefined;

  for (const [index, draft] of drafts.entries()) {
    const number = index + 1;
    const functionName = draft.functionName.trim();
    const rawStdin = draft.stdinText;

    if (rawStdin.length > 8192 || rawStdin.split("\n").length > 129) {
      return fail(`${number}번 테스트의 사용자 입력값(stdin) 제한을 초과했습니다.`);
    }
    // Do not trim stdin: spaces and line breaks can be significant to input().
    if (stdin === undefined && rawStdin !== "") stdin = rawStdin;

    if (!functionName) {
      const untouchedArgs = draft.argsText.trim() === "[]";
      const untouchedKwargs = draft.kwargsText.trim() === "{}";
      if (!untouchedArgs || !untouchedKwargs) {
        return fail(`${number}번 테스트의 함수 인자에 값이 있습니다. 함수 이름을 입력하거나 인자를 [] 및 {}로 초기화해주세요.`);
      }
      // Standalone stdin-only row (or unused extra blank row).
      continue;
    }

    let argsValue: unknown;
    try {
      argsValue = JSON.parse(draft.argsText);
    } catch {
      return fail(`${number}번 테스트의 '순서대로 넣을 값'을 확인해주세요. [5] 또는 ["Jin"]처럼 작성해야 합니다.`);
    }
    if (!Array.isArray(argsValue)) {
      return fail(`${number}번 테스트의 '순서대로 넣을 값'은 대괄호 [ ]로 작성해야 합니다.`);
    }

    let kwargsValue: unknown;
    try {
      kwargsValue = JSON.parse(draft.kwargsText);
    } catch {
      return fail(`${number}번 테스트의 '이름을 지정해 넣을 값'을 확인해주세요. {"punctuation": "?"}처럼 작성하거나 사용하지 않으면 {}를 입력해주세요.`);
    }
    if (kwargsValue === null || typeof kwargsValue !== "object" || Array.isArray(kwargsValue)) {
      return fail(`${number}번 테스트의 '이름을 지정해 넣을 값'은 중괄호 { }로 작성해야 합니다.`);
    }

    functionCases.push({
      function: functionName,
      ...(rawStdin !== "" ? { stdin: rawStdin } : {}),
      args: argsValue as FunctionTestCase["args"],
      kwargs: kwargsValue as FunctionTestCase["kwargs"],
    });
  }

  if (stdin === undefined && functionCases.length === 0) {
    return fail("사용자 입력값(stdin) 또는 함수 이름을 입력해주세요.");
  }

  return {
    ok: true,
    functionCases: functionCases.length > 0 ? functionCases : undefined,
    stdin,
  };
}
