"use client";

import { useState } from "react";
import { applyCodingStyle } from "../lib/api";
import type {
  AnalysisResponse,
  FunctionTestCase,
  StyleApplyResponse,
  SyntaxTag,
  ConceptTag,
} from "../types/analysis";
import type { SharedCodingStyle } from "./useCodingStyles";

export interface StyleApplyResult {
  styleName: string;
  missingSyntaxTags: SyntaxTag[];
  missingConceptTags: ConceptTag[];
  targetAnalysis: AnalysisResponse;
  applyResponse: StyleApplyResponse;
}

const INITIAL_TARGET_CODE = `scores = [45, 60, 72, 88, 91, 100]

total = 0

for score in scores:
    total = total + score

average = total / len(scores)

print(average)`;

export function useStyleApplication(savedStyles: SharedCodingStyle[]) {
  const [selectedStyleId, setSelectedStyleId] = useState("");
  const [targetCode, setTargetCode] = useState(INITIAL_TARGET_CODE);
  const [styleApplyLoading, setStyleApplyLoading] = useState(false);
  const [styleApplyResult, setStyleApplyResult] =
    useState<StyleApplyResult | null>(null);
  const [editableTransformedCode, setEditableTransformedCode] = useState("");

  const selectedStyle = savedStyles.find(
    (style) => style.id === selectedStyleId
  );

  const resetSelection = () => {
    setSelectedStyleId("");
    setStyleApplyResult(null);
    setEditableTransformedCode("");
  };

  const clearDeletedSelection = (id: string) => {
    if (selectedStyleId === id) resetSelection();
  };

  // CAPSTONE_BATCH16_STRICT_VERIFY_V1: forward the opt-in to API.
  const handleApplyStyle = async (
    functionCases?: FunctionTestCase[] | null,
    strictRuntimeValidation: boolean = false,
    stdin?: string,
    stdinCases?: string[]
  ) => {
    if (!selectedStyle) {
      alert("적용할 코딩 스타일을 선택해주세요.");
      return;
    }
    if (!targetCode.trim()) {
      alert("스타일을 적용할 코드를 입력해주세요.");
      return;
    }

    try {
      setStyleApplyLoading(true);
      const applyResponse = await applyCodingStyle(
        targetCode,
        selectedStyle,
        functionCases,
        strictRuntimeValidation,
        stdin,
        stdinCases
      );

      if (!applyResponse.success) {
        alert(applyResponse.error || "코딩 스타일 적용에 실패했습니다.");
        setStyleApplyResult(null);
        setEditableTransformedCode("");
        return;
      }

      if (!applyResponse.final_analysis) {
        alert("스타일 적용 후 최종 코드 분석 결과를 받지 못했습니다.");
        setStyleApplyResult(null);
        setEditableTransformedCode("");
        return;
      }

      const finalAnalysis: AnalysisResponse = {
        success: true,
        syntax_tags: applyResponse.final_analysis.syntax_tags,
        concept_tags: applyResponse.final_analysis.concept_tags,
        metrics: applyResponse.final_analysis.metrics,
        suggestions: [],
        error: null,
      };

      setStyleApplyResult({
        styleName: selectedStyle.name,
        missingSyntaxTags: applyResponse.missing_syntax_tags,
        missingConceptTags: applyResponse.missing_concept_tags,
        targetAnalysis: finalAnalysis,
        applyResponse,
      });
      setEditableTransformedCode(applyResponse.transformed_code);
    } catch (error) {
      console.error("스타일 적용 오류:", error);
      alert("스타일 적용 중 오류가 발생했습니다.");
    } finally {
      setStyleApplyLoading(false);
    }
  };

  return {
    selectedStyleId,
    setSelectedStyleId,
    selectedStyle,
    targetCode,
    setTargetCode,
    styleApplyLoading,
    styleApplyResult,
    setStyleApplyResult,
    editableTransformedCode,
    setEditableTransformedCode,
    handleApplyStyle,
    resetSelection,
    clearDeletedSelection,
  };
}
