"use client";

import { useEffect, useMemo, useState } from "react";
import SyntaxTagSection from "../components/sections/SyntaxTagSection";
import ConceptTagSection from "../components/sections/ConceptTagSection";
import LoginSection from "../components/sections/LoginSection";
import StyleSection from "../components/sections/StyleSection";
import AnalyzeSection from "../components/sections/AnalyzeSection";
import StyleApplySection from "../components/sections/StyleApplySection";
import { analyzeCode, applyCodingStyle } from "../lib/api";
import {
  AnalysisResponse,
  CodingStyle,
  ConceptTag,
  StyleApplyResponse,
  SyntaxTag,
} from "../types/analysis";
import {
  conceptTagDocs,
  filterStyleRelevantSyntaxTags,
  syntaxTagDocs,
} from "./tags";

type MenuType =
  | "analyze"
  | "login"
  | "style"
  | "styleApply"
  | "syntax"
  | "concept";

interface StyleApplyResult {
  styleName: string;
  missingSyntaxTags: SyntaxTag[];
  missingConceptTags: ConceptTag[];
  targetAnalysis: AnalysisResponse;
  applyResponse: StyleApplyResponse;
}

interface AuthUser {
  email: string;
}

type SharedCodingStyle = CodingStyle & {
  is_shared?: boolean;
  shared_from?: string;
  shared_at?: string;
};

const GUEST_EMAIL = "guest";
const STORAGE_KEY_PREFIX = "capstone_saved_coding_styles";
const CURRENT_USER_STORAGE_KEY = "capstone_current_user";

const TEST_ACCOUNTS = [
  { email: "test001@gmail.com", password: "12090" },
  { email: "test002@gmail.com", password: "12090" },
];

const getStyleStorageKey = (email: string) => {
  return `${STORAGE_KEY_PREFIX}_${email}`;
};

const isMenuType = (value: string): value is MenuType => {
  return [
    "analyze",
    "login",
    "style",
    "styleApply",
    "syntax",
    "concept",
  ].includes(value);
};

export default function HomePage() {
  const [menu, setMenu] = useState<MenuType>("analyze");

  const [code, setCode] = useState(`def process(nums):
    result = []
    for i in range(len(nums)):
        if nums[i] % 2 == 0:
            result.append(nums[i])
    return result`);

  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const [syntaxSearch, setSyntaxSearch] = useState("");
  const [conceptSearch, setConceptSearch] = useState("");

  const [savedStyles, setSavedStyles] = useState<SharedCodingStyle[]>([]);
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [shareTargetEmail, setShareTargetEmail] = useState("");
  const [shareModalStyle, setShareModalStyle] =
    useState<SharedCodingStyle | null>(null);
  const [styleName, setStyleName] = useState("");
  const [selectedStyleId, setSelectedStyleId] = useState("");

  const [targetCode, setTargetCode] = useState(`scores = [45, 60, 72, 88, 91, 100]

total = 0

for score in scores:
    total = total + score

average = total / len(scores)

print(average)`);

  const [styleApplyLoading, setStyleApplyLoading] = useState(false);
  const [styleApplyResult, setStyleApplyResult] =
    useState<StyleApplyResult | null>(null);
  const [editableTransformedCode, setEditableTransformedCode] = useState("");

  useEffect(() => {
    const syncMenuWithHash = () => {
      const hashValue = window.location.hash.replace("#", "");

      if (isMenuType(hashValue)) {
        setMenu(hashValue);
      }
    };

    syncMenuWithHash();
    window.addEventListener("hashchange", syncMenuWithHash);

    return () => {
      window.removeEventListener("hashchange", syncMenuWithHash);
    };
  }, []);

  const loadStylesByEmail = (email: string) => {
    const storageKey = getStyleStorageKey(email);
    const raw = localStorage.getItem(storageKey);

    if (!raw) {
      setSavedStyles([]);
      return;
    }

    try {
      const parsed = JSON.parse(raw) as SharedCodingStyle[];
      setSavedStyles(parsed);
    } catch {
      localStorage.removeItem(storageKey);
      setSavedStyles([]);
    }
  };

  useEffect(() => {
    const rawUser = localStorage.getItem(CURRENT_USER_STORAGE_KEY);

    if (!rawUser) {
      loadStylesByEmail(GUEST_EMAIL);
      return;
    }

    try {
      const parsedUser = JSON.parse(rawUser) as AuthUser;
      setCurrentUser(parsedUser);
      loadStylesByEmail(parsedUser.email);
    } catch {
      localStorage.removeItem(CURRENT_USER_STORAGE_KEY);
      loadStylesByEmail(GUEST_EMAIL);
    }
  }, []);

  const saveStylesToStorage = (styles: SharedCodingStyle[]) => {
    const email = currentUser?.email || GUEST_EMAIL;
    const storageKey = getStyleStorageKey(email);

    setSavedStyles(styles);
    localStorage.setItem(storageKey, JSON.stringify(styles));
  };

  const filteredSyntaxTags = useMemo(() => {
    const keyword = syntaxSearch.trim().toLowerCase();

    if (!keyword) return syntaxTagDocs;

    return syntaxTagDocs.filter(
      (item) =>
        item.tag.toLowerCase().includes(keyword) ||
        item.desc.toLowerCase().includes(keyword)
    );
  }, [syntaxSearch]);

  const filteredConceptTags = useMemo(() => {
    const keyword = conceptSearch.trim().toLowerCase();

    if (!keyword) return conceptTagDocs;

    return conceptTagDocs.filter(
      (item) =>
        item.tag.toLowerCase().includes(keyword) ||
        item.desc.toLowerCase().includes(keyword)
    );
  }, [conceptSearch]);

  const createStyleId = () => {
    if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
      return crypto.randomUUID();
    }

    return `${Date.now()}-${Math.random()}`;
  };

  const handleAnalyze = async () => {
    try {
      setLoading(true);

      const data = await analyzeCode(code);

      if (!data.success) {
        alert(data.error || "분석에 실패했습니다.");
        setResult(data);
        return;
      }

      setResult(data);
    } catch (error) {
      console.error("분석 오류:", error);
      alert("백엔드 연결 또는 분석 중 오류가 발생했습니다.");
    } finally {
      setLoading(false);
    }
  };

  const handleSaveStyle = () => {
    if (!result || !result.success) {
      alert("저장할 분석 결과가 없습니다.");
      return;
    }

    const name =
      styleName.trim() || `코딩 스타일 ${savedStyles.length + 1}`;

    const styleSyntaxTags = filterStyleRelevantSyntaxTags(
      result.syntax_tags
    );

    const conceptNames =
      result.concept_tags.map((item) => item.tag).join(", ") ||
      "특정 개념 태그 없음";

    const syntaxNames =
      styleSyntaxTags.map((item) => item.tag).join(", ") ||
      "저장 대상 핵심 문법 태그 없음";

    const newStyle: SharedCodingStyle = {
      id: createStyleId(),
      name,
      description: `이 코딩 스타일은 개념 태그(${conceptNames})를 코드 구조 기준으로 사용하고, 저장용 핵심 문법 태그(${syntaxNames})를 적용 가능한 문법 한계로 사용한다.`,
      syntax_tags: styleSyntaxTags,
      concept_tags: result.concept_tags,
      metrics: result.metrics,
      created_at: new Date().toLocaleString(),
      is_shared: false,
    };

    const nextStyles = [newStyle, ...savedStyles];

    saveStylesToStorage(nextStyles);
    setStyleName("");
    alert("코딩 스타일이 저장되었습니다.");
  };

  const handleDeleteStyle = (id: string) => {
    const nextStyles = savedStyles.filter((style) => style.id !== id);
    saveStylesToStorage(nextStyles);

    if (selectedStyleId === id) {
      setSelectedStyleId("");
      setStyleApplyResult(null);
      setEditableTransformedCode("");
    }
  };

  const handleLogin = () => {
    const account = TEST_ACCOUNTS.find(
      (item) =>
        item.email === loginEmail.trim() &&
        item.password === loginPassword
    );

    if (!account) {
      alert("이메일 또는 비밀번호가 올바르지 않습니다.");
      return;
    }

    const nextUser = { email: account.email };

    setCurrentUser(nextUser);
    localStorage.setItem(
      CURRENT_USER_STORAGE_KEY,
      JSON.stringify(nextUser)
    );

    loadStylesByEmail(account.email);
    setLoginEmail("");
    setLoginPassword("");
    setSelectedStyleId("");
    setStyleApplyResult(null);
    setEditableTransformedCode("");

    alert(`${account.email} 계정으로 로그인되었습니다.`);
  };

  const handleLogout = () => {
    setCurrentUser(null);
    localStorage.removeItem(CURRENT_USER_STORAGE_KEY);
    loadStylesByEmail(GUEST_EMAIL);
    setSelectedStyleId("");
    setStyleApplyResult(null);
    setEditableTransformedCode("");

    alert("로그아웃되었습니다.");
  };

  const handleOpenShareModal = (style: SharedCodingStyle) => {
    if (!currentUser) {
      alert("로그인이 필요한 서비스입니다.");
      return;
    }

    setShareTargetEmail("");
    setShareModalStyle(style);
  };

  const handleShareStyle = () => {
    if (!currentUser) {
      alert("로그인이 필요한 서비스입니다.");
      return;
    }

    if (!shareModalStyle) {
      alert("공유할 코딩 스타일을 찾을 수 없습니다.");
      return;
    }

    const targetEmail = shareTargetEmail.trim();

    if (!targetEmail) {
      alert("공유할 계정의 이메일을 입력해주세요.");
      return;
    }

    if (targetEmail === currentUser.email) {
      alert("현재 로그인한 본인 계정으로는 공유할 수 없습니다.");
      return;
    }

    const targetAccount = TEST_ACCOUNTS.find(
      (account) => account.email === targetEmail
    );

    if (!targetAccount) {
      alert("현재 등록된 테스트 계정으로만 공유할 수 있습니다.");
      return;
    }

    const targetStorageKey = getStyleStorageKey(targetEmail);
    const rawTargetStyles = localStorage.getItem(targetStorageKey);

    let targetStyles: SharedCodingStyle[] = [];

    if (rawTargetStyles) {
      try {
        targetStyles = JSON.parse(
          rawTargetStyles
        ) as SharedCodingStyle[];
      } catch {
        targetStyles = [];
      }
    }

    const sharedStyle: SharedCodingStyle = {
      ...shareModalStyle,
      id: createStyleId(),
      name: shareModalStyle.name,
      is_shared: true,
      shared_from: currentUser.email,
      shared_at: new Date().toLocaleString(),
      created_at: new Date().toLocaleString(),
    };

    localStorage.setItem(
      targetStorageKey,
      JSON.stringify([sharedStyle, ...targetStyles])
    );

    setShareModalStyle(null);
    setShareTargetEmail("");

    alert(`${targetEmail} 계정으로 코딩 스타일을 공유했습니다.`);
  };

  const handleApplyStyle = async () => {
    const selectedStyle = savedStyles.find(
      (style) => style.id === selectedStyleId
    );

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
        selectedStyle
      );

      if (!applyResponse.success) {
        alert(
          applyResponse.error || "코딩 스타일 적용에 실패했습니다."
        );

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

  const selectedStyle = savedStyles.find(
    (style) => style.id === selectedStyleId
  );

  return (
    <>
      {menu === "analyze" && (
        <AnalyzeSection
          code={code}
          setCode={setCode}
          loading={loading}
          handleAnalyze={handleAnalyze}
          result={result}
          styleName={styleName}
          setStyleName={setStyleName}
          handleSaveStyle={handleSaveStyle}
        />
      )}

      {menu === "login" && (
        <LoginSection
          currentUser={currentUser}
          loginEmail={loginEmail}
          setLoginEmail={setLoginEmail}
          loginPassword={loginPassword}
          setLoginPassword={setLoginPassword}
          handleLogin={handleLogin}
          handleLogout={handleLogout}
        />
      )}

      {menu === "style" && (
        <StyleSection
          currentUser={currentUser}
          savedStyles={savedStyles}
          shareModalStyle={shareModalStyle}
          shareTargetEmail={shareTargetEmail}
          setShareTargetEmail={setShareTargetEmail}
          setShareModalStyle={setShareModalStyle}
          handleOpenShareModal={handleOpenShareModal}
          handleDeleteStyle={handleDeleteStyle}
          handleShareStyle={handleShareStyle}
        />
      )}

      {menu === "styleApply" && (
        <StyleApplySection
          selectedStyleId={selectedStyleId}
          setSelectedStyleId={setSelectedStyleId}
          savedStyles={savedStyles}
          selectedStyle={selectedStyle}
          targetCode={targetCode}
          setTargetCode={setTargetCode}
          handleApplyStyle={handleApplyStyle}
          styleApplyLoading={styleApplyLoading}
          styleApplyResult={styleApplyResult}
          setStyleApplyResult={setStyleApplyResult}
          editableTransformedCode={editableTransformedCode}
          setEditableTransformedCode={setEditableTransformedCode}
        />
      )}

      {menu === "syntax" && (
        <SyntaxTagSection
          syntaxSearch={syntaxSearch}
          setSyntaxSearch={setSyntaxSearch}
          filteredSyntaxTags={filteredSyntaxTags}
        />
      )}

      {menu === "concept" && (
        <ConceptTagSection
          conceptSearch={conceptSearch}
          setConceptSearch={setConceptSearch}
          filteredConceptTags={filteredConceptTags}
        />
      )}
    </>
  );
}