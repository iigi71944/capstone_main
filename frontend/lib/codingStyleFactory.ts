
import type {
  AnalysisResponse,
  CodingStyle,
  ConceptTag,
  SyntaxTag,
} from "../types/analysis";

import {
  filterStyleRelevantSyntaxTags,
} from "../app/tags";

/**
 * 실제 저장되는 코딩 스타일 데이터 구조입니다.
 *
 * 기존 CodingStyle 형식을 유지하면서
 * 최초 생성 시 공유 여부를 false로 지정합니다.
 */
export type NewCodingStyle = CodingStyle & {
  is_shared: false;
};

/**
 * 코딩 스타일의 고유 ID와 생성 시각입니다.
 *
 * JSON 미리보기와 실제 저장에서 동일한
 * ID와 생성 시각을 사용하기 위한 구조입니다.
 */
export interface CodingStyleIdentity {
  id: string;
  created_at: string;
}

/**
 * 코딩 스타일 생성에 필요한 정보입니다.
 */
export interface CodingStyleBuildOptions
  extends CodingStyleIdentity {
  name: string;
  fallbackName: string;
}

/**
 * 새로운 코딩 스타일의 고유 ID를 생성합니다.
 *
 * 기존 page.tsx의 ID 생성 방식을 유지합니다.
 */
export function createCodingStyleId(): string {
  if (
    typeof crypto !== "undefined" &&
    "randomUUID" in crypto
  ) {
    return crypto.randomUUID();
  }

  return `${Date.now()}-${Math.random()}`;
}

/**
 * 코딩 스타일의 식별 정보를 생성합니다.
 *
 * 분석 완료 시 생성한 값을 미리보기와
 * 실제 저장에서 공통으로 사용합니다.
 */
export function createCodingStyleIdentity():
  CodingStyleIdentity {
  return {
    id: createCodingStyleId(),
    created_at: new Date().toLocaleString(),
  };
}

/**
 * 사용자 입력 스타일 이름을 정리합니다.
 *
 * 이름을 입력하지 않은 경우 기본 이름을 사용합니다.
 */
export function resolveCodingStyleName(
  name: string,
  fallbackName: string
): string {
  return name.trim() || fallbackName;
}

/**
 * 저장할 문법 태그를 선택합니다.
 *
 * 기존 프로젝트의 문법 태그 필터링 규칙을
 * 그대로 적용합니다.
 */
export function getStorableSyntaxTags(
  syntaxTags: SyntaxTag[]
): SyntaxTag[] {
  return filterStyleRelevantSyntaxTags(
    syntaxTags
  );
}

/**
 * 저장할 개념 태그를 반환합니다.
 *
 * 기존 저장 로직과 동일하게 분석된
 * 개념 태그 전체를 유지합니다.
 */
export function getStorableConceptTags(
  conceptTags: ConceptTag[]
): ConceptTag[] {
  return conceptTags;
}

/**
 * 분석된 문법 태그와 개념 태그로
 * 코딩 스타일의 설명을 생성합니다.
 *
 * 기존 page.tsx에서 사용하던 설명 문장을
 * 변경하지 않고 유지합니다.
 */
export function buildCodingStyleDescription(
  syntaxTags: SyntaxTag[],
  conceptTags: ConceptTag[]
): string {
  const conceptNames =
    conceptTags
      .map((item) => item.tag)
      .join(", ") ||
    "특정 개념 태그 없음";

  const syntaxNames =
    syntaxTags
      .map((item) => item.tag)
      .join(", ") ||
    "저장 대상 핵심 문법 태그 없음";

  return (
    `이 코딩 스타일은 개념 태그(${conceptNames})를 코드 구조 기준으로 사용하고, ` +
    `저장용 핵심 문법 태그(${syntaxNames})를 적용 가능한 문법 한계로 사용한다.`
  );
}

/**
 * 코드 분석 결과를 실제 저장 가능한
 * 코딩 스타일 객체로 변환합니다.
 *
 * 저장 데이터:
 *
 * {
 *   id,
 *   name,
 *   description,
 *   syntax_tags,
 *   concept_tags,
 *   metrics,
 *   created_at,
 *   is_shared
 * }
 *
 * 기존 기능 유지 사항:
 *
 * 1. 문법 태그는 기존 필터링 규칙 사용
 * 2. 개념 태그 전체 저장
 * 3. 메트릭 전체 저장
 * 4. 기존 설명 생성 방식 유지
 * 5. 원본 Python 코드는 저장하지 않음
 * 6. ID와 생성 시각은 전달받은 값 사용
 * 7. 초기 공유 상태는 false
 */
export function buildCodingStyleFromAnalysis(
  analysis: AnalysisResponse,
  options: CodingStyleBuildOptions
): NewCodingStyle {
  if (!analysis.success) {
    throw new Error(
      "분석에 실패한 코드는 코딩 스타일로 저장할 수 없습니다."
    );
  }

  const syntaxTags =
    getStorableSyntaxTags(
      analysis.syntax_tags
    );

  const conceptTags =
    getStorableConceptTags(
      analysis.concept_tags
    );

  const description =
    buildCodingStyleDescription(
      syntaxTags,
      conceptTags
    );

  const style: NewCodingStyle = {
    id: options.id,

    name: resolveCodingStyleName(
      options.name,
      options.fallbackName
    ),

    description,

    syntax_tags: syntaxTags,

    concept_tags: conceptTags,

    metrics: analysis.metrics,

    // CAPSTONE_BATCH35_4_METRIC_VERSION_V1: new snapshots explicitly declare the 81-metric schema.
    metrics_version: 1,

    // CAPSTONE_FORMATTING_STYLE_GIT_ALIGNED_V2: 코드에서 추출한 서식 취향을 함께 저장합니다.
    formatting_style: analysis.formatting_style,

    created_at: options.created_at,

    is_shared: false,
  };

  return style;
}

/**
 * 코딩 스타일 객체를 JSON 문자열로 변환합니다.
 *
 * 모든 항목을 표시하며 데이터를 축약하지 않습니다.
 *
 * JSON 출력 영역은 AnalyzeSection.tsx에서
 * 높이를 자동 확장하도록 구성합니다.
 */
export function serializeCodingStyle(
  style: NewCodingStyle
): string {
  return JSON.stringify(
    style,
    null,
    2
  );
}
