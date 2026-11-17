/** 저장된 코딩 스타일의 이름 충돌을 검사하는 순수 함수입니다. */
export const DUPLICATE_STYLE_NAME_MESSAGE =
  "저장하려는 코딩 스타일 이름이 중복됩니다. 다른 이름을 작성해주세요";

/** 이름 앞뒤 공백, 영문 대소문자, 유니코드 조합형 차이를 정규화합니다. */
export function normalizeCodingStyleName(name: string): string {
  return name.trim().normalize("NFC").toLowerCase();
}

/** 공유받은 스타일도 포함한 해당 계정의 저장 목록에서 중복을 검사합니다. */
export function isDuplicateCodingStyleName(
  name: string,
  styles: readonly { name: string }[]
): boolean {
  const expected = normalizeCodingStyleName(name);
  return styles.some(
    (style) =>
      typeof style?.name === "string" &&
      normalizeCodingStyleName(style.name) === expected
  );
}
