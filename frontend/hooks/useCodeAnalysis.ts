"use client";

import { useMemo, useRef, useState } from "react";
// CAPSTONE_FORMATTING_STYLE_GIT_ALIGNED_V2
import { analyzeCode, analyzeFormattingStyle } from "../lib/api";
import {
  buildCodingStyleFromAnalysis,
  createCodingStyleIdentity,
} from "../lib/codingStyleFactory";
import type { CodingStyleIdentity } from "../lib/codingStyleFactory";
import type { AnalysisResponse } from "../types/analysis";

const INITIAL_CODE = `def process(nums):
    result = []
    for i in range(len(nums)):
        if nums[i] % 2 == 0:
            result.append(nums[i])
    return result`;

export function useCodeAnalysis(savedStyleCount: number) {
  const [code, setCodeState] = useState(INITIAL_CODE);
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [styleName, setStyleName] = useState("");
  const [identity, setIdentity] = useState<CodingStyleIdentity | null>(null);
  const requestVersion = useRef(0);

  const setCode = (value: string) => {
    requestVersion.current += 1;
    setCodeState(value);
    setResult(null);
    setIdentity(null);
    setLoading(false);
  };

  const stylePreview = useMemo(() => {
    if (!result?.success || !identity) {
      return null;
    }

    return buildCodingStyleFromAnalysis(result, {
      id: identity.id,
      created_at: identity.created_at,
      name: styleName,
      fallbackName: `코딩 스타일 ${savedStyleCount + 1}`,
    });
  }, [result, identity, styleName, savedStyleCount]);

  const handleAnalyze = async () => {
    const requestId = ++requestVersion.current;
    setLoading(true);
    setResult(null);
    setIdentity(null);

    try {
      const data = await analyzeCode(code);
      if (requestVersion.current !== requestId) return;

      if (!data.success) {
        alert(data.error || "분석에 실패했습니다.");
        setResult(data);
        return;
      }

      // 코드 분석이 성공한 경우에만 서식을 추가 분석합니다.
      const formattingStyle = await analyzeFormattingStyle(code);
      if (requestVersion.current !== requestId) return;
      setIdentity(createCodingStyleIdentity());
      setResult({ ...data, formatting_style: formattingStyle });
    } catch (error) {
      if (requestVersion.current !== requestId) return;
      console.error("분석 오류:", error);
      alert("백엔드 연결 또는 분석 중 오류가 발생했습니다.");
    } finally {
      if (requestVersion.current === requestId) {
        setLoading(false);
      }
    }
  };

  const prepareNextStyle = () => {
    setStyleName("");
    setIdentity(createCodingStyleIdentity());
  };

  return {
    code,
    setCode,
    result,
    loading,
    styleName,
    setStyleName,
    stylePreview,
    handleAnalyze,
    prepareNextStyle,
  };
}
