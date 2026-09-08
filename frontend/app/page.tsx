"use client";

import { useEffect, useMemo, useState } from "react";
import CodeEditor from "../components/editor/CodeEditor";
import CodeViewer from "../components/editor/CodeViewer";
import { analyzeCode, applyCodingStyle, improveCode } from "../lib/api";
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

type ImproveMode = "beginner" | "concise" | "structured" | null;
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
  return ["analyze", "login", "style", "styleApply", "syntax", "concept"].includes(value);
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

  const [selectedMode, setSelectedMode] = useState<ImproveMode>(null);
  const [improvementLoading, setImprovementLoading] = useState(false);
  const [originalCode, setOriginalCode] = useState("");
  const [improvedCode, setImprovedCode] = useState("");
  const [improvementSummary, setImprovementSummary] = useState("");

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

  const handleImprove = async (mode: ImproveMode) => {
    if (!mode) return;

    try {
      setImprovementLoading(true);
      setSelectedMode(mode);

      const data = await improveCode(code, mode);

      if (!data.success) {
        alert(data.error || "코드 개선에 실패했습니다.");
        return;
      }

      setOriginalCode(data.original_code);
      setImprovedCode(data.improved_code);
      setImprovementSummary(data.summary || "");
    } catch (error) {
      console.error("개선 오류:", error);
      alert("코드 개선 중 오류가 발생했습니다.");
    } finally {
      setImprovementLoading(false);
    }
  };

  const handleCopyText = async (text: string, message: string) => {
    try {
      await navigator.clipboard.writeText(text);
      alert(message);
    } catch (error) {
      console.error("복사 오류:", error);
      alert("코드 복사에 실패했습니다.");
    }
  };

  const handleSaveStyle = () => {
    if (!result || !result.success) {
      alert("저장할 분석 결과가 없습니다.");
      return;
    }

    const name = styleName.trim() || `코딩 스타일 ${savedStyles.length + 1}`;
    const styleSyntaxTags = filterStyleRelevantSyntaxTags(result.syntax_tags);

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
      (item) => item.email === loginEmail.trim() && item.password === loginPassword
    );

    if (!account) {
      alert("이메일 또는 비밀번호가 올바르지 않습니다.");
      return;
    }

    const nextUser = { email: account.email };
    setCurrentUser(nextUser);
    localStorage.setItem(CURRENT_USER_STORAGE_KEY, JSON.stringify(nextUser));
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

    const targetAccount = TEST_ACCOUNTS.find((account) => account.email === targetEmail);

    if (!targetAccount) {
      alert("현재 등록된 테스트 계정으로만 공유할 수 있습니다.");
      return;
    }

    const targetStorageKey = getStyleStorageKey(targetEmail);
    const rawTargetStyles = localStorage.getItem(targetStorageKey);
    let targetStyles: SharedCodingStyle[] = [];

    if (rawTargetStyles) {
      try {
        targetStyles = JSON.parse(rawTargetStyles) as SharedCodingStyle[];
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

      const targetAnalysis = await analyzeCode(targetCode);

      if (!targetAnalysis.success) {
        alert(targetAnalysis.error || "대상 코드 분석에 실패했습니다.");
        setStyleApplyResult(null);
        setEditableTransformedCode("");
        return;
      }

      const applyResponse = await applyCodingStyle(targetCode, selectedStyle);

      if (!applyResponse.success) {
        alert(applyResponse.error || "코딩 스타일 적용에 실패했습니다.");
        setStyleApplyResult(null);
        setEditableTransformedCode("");
        return;
      }

      const targetSyntaxSet = new Set(
        targetAnalysis.syntax_tags.map((item) => item.tag)
      );

      const targetConceptSet = new Set(
        targetAnalysis.concept_tags.map((item) => item.tag)
      );

      const missingSyntaxTags = selectedStyle.syntax_tags.filter(
        (item) => !targetSyntaxSet.has(item.tag)
      );

      const missingConceptTags = selectedStyle.concept_tags.filter(
        (item) => !targetConceptSet.has(item.tag)
      );

      setStyleApplyResult({
        styleName: selectedStyle.name,
        missingSyntaxTags,
        missingConceptTags,
        targetAnalysis,
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
        <div className="space-y-6">
          <section className="rounded-2xl border border-slate-300 bg-white p-5 shadow-sm">
            <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 mb-3">
              <div>
                <h2 className="text-2xl font-bold text-slate-900">코드 입력</h2>
                <p className="text-slate-600 mt-1">
                  해당 영역에 분석할 코드를 입력해 주세요.
                </p>
              </div>

              <span className="self-start lg:self-auto rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-700 border border-slate-200">
                Python Only
              </span>
            </div>

            <CodeEditor
              code={code}
              setCode={setCode}
              highlights={result?.highlights || []}
            />

            <div className="mt-4 flex flex-wrap items-center gap-3">
              <button
                onClick={handleAnalyze}
                disabled={loading}
                className="inline-flex items-center justify-center whitespace-nowrap min-w-[120px] px-5 py-2.5 rounded-lg bg-slate-900 text-white hover:bg-slate-700 disabled:bg-slate-400 transition"
              >
                {loading ? "분석 중..." : "분석하기"}
              </button>

              <span className="text-sm text-slate-600">
                분석 후 현재 결과를 코딩 스타일로 저장할 수 있습니다.
              </span>
            </div>
          </section>

          <section className="rounded-2xl border border-slate-300 bg-white p-5 shadow-sm">
            <h2 className="text-2xl font-bold text-slate-900 mb-4">
              분석 결과
            </h2>

            {!result && (
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-slate-600">
                아직 분석 결과가 없습니다. 위 코드 입력창에 Python 코드를 작성한 뒤
                분석하기 버튼을 눌러 주세요.
              </div>
            )}

            {result && (
              <div className="space-y-6">
                {!result.success && (
                  <div className="rounded-lg border border-red-300 bg-red-50 p-4">
                    <h3 className="font-semibold text-red-700 mb-1">오류</h3>
                    <p className="text-sm text-red-700">
                      {result.error || "알 수 없는 오류가 발생했습니다."}
                    </p>
                  </div>
                )}

                {result.success && (
                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                    <h3 className="font-semibold mb-2 text-slate-900">
                      현재 분석 결과를 코딩 스타일로 저장
                    </h3>
                    <p className="text-sm text-slate-600 mb-3">
                      추출된 문법 태그와 개념 태그의 집합을 하나의 코딩 스타일로
                      저장합니다.
                    </p>

                    <div className="flex flex-col sm:flex-row gap-3">
                      <input
                        type="text"
                        value={styleName}
                        onChange={(e) => setStyleName(e.target.value)}
                        placeholder="스타일 이름 입력"
                        className="flex-1 rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm outline-none focus:border-slate-500"
                      />

                      <button
                        onClick={handleSaveStyle}
                        className="whitespace-nowrap rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
                      >
                        스타일 저장
                      </button>
                    </div>
                  </div>
                )}

                {result.success && (
                  <>
                    <div>
                      <h3 className="font-semibold mb-2 text-slate-900">
                        문법 태그
                      </h3>
                      {result.syntax_tags.length === 0 ? (
                        <p className="text-sm text-slate-500">
                          문법 태그가 없습니다.
                        </p>
                      ) : (
                        <div className="flex flex-wrap gap-2">
                          {result.syntax_tags.map((item, idx) => (
                            <span
                              key={idx}
                              className="px-3 py-1 rounded-full bg-blue-100 text-blue-800 text-sm font-medium"
                            >
                              {item.tag}
                              {item.count ? ` (${item.count})` : ""}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>

                    <div>
                      <h3 className="font-semibold mb-2 text-slate-900">
                        개념 태그
                      </h3>
                      {result.concept_tags.length === 0 ? (
                        <p className="text-sm text-slate-500">
                          아직 개념 태그가 없습니다.
                        </p>
                      ) : (
                        <div className="space-y-3">
                          {result.concept_tags.map((item, idx) => (
                            <div
                              key={idx}
                              className="rounded-xl border border-purple-200 bg-purple-50 p-3"
                            >
                              <span className="inline-block px-3 py-1 rounded-full bg-purple-100 text-purple-800 text-sm font-medium mb-2">
                                {item.tag}
                              </span>
                              <p className="text-sm text-slate-700">
                                {"reason" in item && item.reason
                                  ? item.reason
                                  : `score: ${item.score ?? "-"}`}
                              </p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    <div>
                      <h3 className="font-semibold mb-2 text-slate-900">
                        메트릭
                      </h3>
                      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-3">
                        {Object.entries(result.metrics).map(([key, value]) => (
                          <div
                            key={key}
                            className="rounded-xl border border-slate-200 bg-slate-50 p-3"
                          >
                            <div className="text-lg font-bold text-slate-900">
                              {value}
                            </div>
                            <div className="text-xs text-slate-600 mt-1 break-words">
                              {key}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div>
                      <div className="flex flex-wrap items-center gap-2 mb-2">
                        <h3 className="font-semibold text-slate-900">
                          개선 제안
                        </h3>

                        <button
                          onClick={() => handleImprove("beginner")}
                          disabled={improvementLoading}
                          className={`px-3 py-1 rounded-lg text-sm border transition ${
                            selectedMode === "beginner"
                              ? "bg-green-200 border-green-400 text-green-900"
                              : "bg-white border-slate-300 text-slate-700 hover:bg-slate-100"
                          }`}
                        >
                          학습 친화형
                        </button>

                        <button
                          onClick={() => handleImprove("concise")}
                          disabled={improvementLoading}
                          className={`px-3 py-1 rounded-lg text-sm border transition ${
                            selectedMode === "concise"
                              ? "bg-blue-200 border-blue-400 text-blue-900"
                              : "bg-white border-slate-300 text-slate-700 hover:bg-slate-100"
                          }`}
                        >
                          간결성 중심형
                        </button>

                        <button
                          onClick={() => handleImprove("structured")}
                          disabled={improvementLoading}
                          className={`px-3 py-1 rounded-lg text-sm border transition ${
                            selectedMode === "structured"
                              ? "bg-purple-200 border-purple-400 text-purple-900"
                              : "bg-white border-slate-300 text-slate-700 hover:bg-slate-100"
                          }`}
                        >
                          구조 중심형
                        </button>
                      </div>

                      {improvementLoading && (
                        <p className="text-sm text-slate-600">
                          개선 코드를 생성하는 중입니다...
                        </p>
                      )}

                      {selectedMode && !improvementLoading && (
                        <div className="space-y-4">
                          <p className="text-sm text-slate-700">
                            {improvementSummary ||
                              "선택한 개선 모드가 적용된 전체 코드입니다."}
                          </p>

                          <div className="grid grid-cols-1 2xl:grid-cols-2 gap-4">
                            <CodeViewer
                              title="변경 전 코드"
                              code={originalCode || code}
                              readOnly={true}
                            />

                            <div className="min-w-0">
                              <CodeViewer
                                title="개선된 전체 코드"
                                code={improvedCode}
                                readOnly={false}
                                onChange={setImprovedCode}
                              />

                              <div className="mt-3 flex justify-end">
                                <button
                                  onClick={() =>
                                    handleCopyText(
                                      improvedCode,
                                      "개선된 코드가 복사되었습니다."
                                    )
                                  }
                                  className="px-4 py-2 rounded-lg bg-slate-900 text-white hover:bg-slate-700 transition"
                                >
                                  개선 코드 복사
                                </button>
                              </div>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </>
                )}
              </div>
            )}
          </section>
        </div>
      )}

      {menu === "login" && (
        <div className="bg-white border border-slate-300 rounded-2xl p-6 shadow-sm">
          <h2 className="text-2xl font-semibold text-slate-900 mb-3">로그인</h2>

          {currentUser ? (
            <div className="space-y-4">
              <div className="rounded-xl border border-green-200 bg-green-50 p-4">
                <p className="text-sm font-semibold text-green-800">
                  현재 로그인 계정
                </p>
                <p className="text-lg font-bold text-green-900 mt-1">
                  {currentUser.email}
                </p>
                <p className="text-sm text-slate-700 mt-2">
                  현재 계정 기준으로 코딩 스타일 목록이 저장되고 공유됩니다.
                </p>
              </div>

              <button
                onClick={handleLogout}
                className="px-4 py-2 rounded-xl bg-slate-900 text-white hover:bg-slate-700 transition"
              >
                로그아웃
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              <p className="text-slate-600 leading-relaxed">
                테스트용 계정으로 로그인하면 계정별 코딩 스타일 저장 목록과 공유 기능을 사용할 수 있습니다.
              </p>

              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
                <p className="font-semibold text-slate-900 mb-2">테스트 계정</p>
                <p>계정1: test001@gmail.com / 12090</p>
                <p>계정2: test002@gmail.com / 12090</p>
              </div>

              <div className="grid grid-cols-1 gap-3 max-w-md">
                <input
                  type="email"
                  value={loginEmail}
                  onChange={(e) => setLoginEmail(e.target.value)}
                  placeholder="이메일"
                  className="rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none focus:border-slate-500"
                />

                <input
                  type="password"
                  value={loginPassword}
                  onChange={(e) => setLoginPassword(e.target.value)}
                  placeholder="비밀번호"
                  className="rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none focus:border-slate-500"
                />

                <button
                  onClick={handleLogin}
                  className="rounded-xl bg-slate-900 px-4 py-3 text-sm font-medium text-white hover:bg-slate-700 transition"
                >
                  로그인
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {menu === "style" && (
        <div className="bg-white border border-slate-300 rounded-2xl p-6 shadow-sm">
          <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-3 mb-5">
            <div>
              <h2 className="text-2xl font-semibold text-slate-900 mb-2">
                스타일 목록
              </h2>
              <p className="text-slate-600 leading-relaxed">
                분석 결과에서 저장한 코딩 스타일 목록입니다.
              </p>
              <p className="text-sm text-slate-500 mt-2">
                현재 계정: {currentUser ? currentUser.email : "비로그인 임시 저장소"}
              </p>
            </div>

            <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
              총 {savedStyles.length}개 스타일
            </div>
          </div>

          {savedStyles.length === 0 ? (
            <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-5 text-sm text-slate-500">
              저장된 코딩 스타일이 없습니다.
            </div>
          ) : (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 items-start">
              {savedStyles.map((style) => {
                const isShared = Boolean(style.is_shared);

                return (
                  <div
                    key={style.id}
                    className={`rounded-xl border p-4 shadow-sm h-auto self-start ${
                      isShared
                        ? "border-green-300 bg-green-50"
                        : "border-slate-200 bg-slate-50"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3 mb-3">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="font-semibold text-slate-900 break-words">
                            {style.name}
                          </h3>

                          {isShared && (
                            <span className="rounded-full bg-green-100 px-2.5 py-1 text-xs font-semibold text-green-800 border border-green-200">
                              공유받은 스타일
                            </span>
                          )}
                        </div>

                        <p className="text-xs text-slate-500 mt-1">
                          생성일: {style.created_at}
                        </p>

                        {isShared && style.shared_from && (
                          <p className="text-xs text-green-700 mt-1">
                            공유한 계정: {style.shared_from}
                          </p>
                        )}
                      </div>

                      <div className="flex shrink-0 gap-2">
                        <button
                          onClick={() => handleOpenShareModal(style)}
                          className="text-xs px-3 py-1 rounded-lg border border-blue-200 text-blue-700 bg-white hover:bg-blue-50"
                        >
                          공유
                        </button>

                        <button
                          onClick={() => handleDeleteStyle(style.id)}
                          className="text-xs px-3 py-1 rounded-lg border border-red-200 text-red-600 bg-white hover:bg-red-50"
                        >
                          삭제
                        </button>
                      </div>
                    </div>

                    <p className="text-sm text-slate-700 leading-relaxed mb-4 line-clamp-3">
                      {style.description}
                    </p>

                    <div className="mb-3">
                      <h4 className="text-sm font-semibold text-blue-800 mb-2">
                        문법 태그 한계
                      </h4>
                      {style.syntax_tags.length === 0 ? (
                        <p className="text-xs text-slate-500">
                          저장된 핵심 문법 태그가 없습니다.
                        </p>
                      ) : (
                        <div className="flex flex-wrap gap-2 max-h-24 overflow-y-auto pr-1">
                          {style.syntax_tags.map((tag, idx) => (
                            <span
                              key={idx}
                              className="px-2.5 py-1 rounded-full bg-blue-100 text-blue-800 text-xs font-medium"
                            >
                              {tag.tag}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>

                    <div>
                      <h4 className="text-sm font-semibold text-purple-800 mb-2">
                        개념 태그 구조
                      </h4>
                      {style.concept_tags.length === 0 ? (
                        <p className="text-xs text-slate-500">
                          저장된 개념 태그가 없습니다.
                        </p>
                      ) : (
                        <div className="flex flex-wrap gap-2 max-h-28 overflow-y-auto pr-1">
                          {style.concept_tags.map((tag, idx) => (
                            <span
                              key={idx}
                              className="px-2.5 py-1 rounded-full bg-purple-100 text-purple-800 text-xs font-medium"
                            >
                              {tag.tag}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {shareModalStyle && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
              <div className="w-full max-w-md rounded-2xl bg-white border border-slate-300 p-5 shadow-xl">
                <h3 className="text-lg font-semibold text-slate-900 mb-2">
                  코딩 스타일 공유
                </h3>

                <p className="text-sm text-slate-600 mb-4">
                  공유할 계정의 이메일을 작성해주십시오.
                </p>

                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 mb-4">
                  <p className="text-sm font-semibold text-slate-900">
                    {shareModalStyle.name}
                  </p>
                  <p className="text-xs text-slate-500 mt-1">
                    현재 공유 가능 계정: test001@gmail.com, test002@gmail.com
                  </p>
                </div>

                <input
                  type="email"
                  value={shareTargetEmail}
                  onChange={(e) => setShareTargetEmail(e.target.value)}
                  placeholder="공유할 계정 이메일"
                  className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none focus:border-slate-500 mb-4"
                />

                <div className="flex justify-end gap-2">
                  <button
                    onClick={() => {
                      setShareModalStyle(null);
                      setShareTargetEmail("");
                    }}
                    className="px-4 py-2 rounded-xl border border-slate-300 text-slate-700 hover:bg-slate-50"
                  >
                    취소
                  </button>

                  <button
                    onClick={handleShareStyle}
                    className="px-4 py-2 rounded-xl bg-slate-900 text-white hover:bg-slate-700"
                  >
                    공유하기
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {menu === "styleApply" && (
        <div className="space-y-6">
          <section className="bg-white border border-slate-300 rounded-2xl p-6 shadow-sm">
            <h2 className="text-2xl font-semibold text-slate-900 mb-2">
              스타일 적용
            </h2>
            <p className="text-slate-600 mb-5 leading-relaxed">
              저장된 코딩 스타일을 선택하고, 다른 코드에 실제 변환을 적용합니다.
            </p>

            <div className="mb-5">
              <label className="block text-sm font-semibold text-slate-800 mb-2">
                적용할 코딩 스타일 선택
              </label>

              <select
                value={selectedStyleId}
                onChange={(e) => {
                  setSelectedStyleId(e.target.value);
                  setStyleApplyResult(null);
                  setEditableTransformedCode("");
                }}
                className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none focus:border-slate-500"
              >
                <option value="">코딩 스타일을 선택하세요</option>
                {savedStyles.map((style) => (
                  <option key={style.id} value={style.id}>
                    {style.name}
                  </option>
                ))}
              </select>
            </div>

            {selectedStyle && (
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 mb-5">
                <h3 className="font-semibold text-slate-900 mb-2">
                  선택된 스타일 설명
                </h3>
                <p className="text-sm text-slate-700 leading-relaxed">
                  {selectedStyle.description}
                </p>
              </div>
            )}

            <div>
              <h3 className="font-semibold text-slate-900 mb-3">
                스타일을 적용할 코드 입력
              </h3>
              <CodeEditor
                code={targetCode}
                setCode={setTargetCode}
                highlights={[]}
              />
            </div>

            <div className="mt-4">
              <button
                onClick={handleApplyStyle}
                disabled={styleApplyLoading}
                className="inline-flex items-center justify-center whitespace-nowrap min-w-[160px] px-5 py-2.5 rounded-xl bg-slate-900 text-white hover:bg-slate-700 disabled:bg-slate-400 transition font-medium"
              >
                {styleApplyLoading ? "변환 중..." : "스타일 실제 적용"}
              </button>
            </div>
          </section>

          {styleApplyResult && (
            <section className="bg-white border border-slate-300 rounded-2xl p-6 shadow-sm">
              <h2 className="text-xl font-semibold text-slate-900 mb-4">
                스타일 적용 결과
              </h2>

              <div className="grid grid-cols-1 2xl:grid-cols-2 gap-4 mb-5">
                <CodeViewer
                  title="변환 전 코드"
                  code={styleApplyResult.applyResponse.original_code}
                  readOnly={true}
                />

                <div>
                  <CodeViewer
                    title="스타일 적용 후 코드"
                    code={editableTransformedCode}
                    readOnly={false}
                    onChange={setEditableTransformedCode}
                  />

                  <div className="mt-3 flex justify-end">
                    <button
                      onClick={() =>
                        handleCopyText(
                          editableTransformedCode,
                          "스타일 적용 코드가 복사되었습니다."
                        )
                      }
                      className="px-4 py-2 rounded-lg bg-slate-900 text-white hover:bg-slate-700 transition"
                    >
                      적용 코드 복사
                    </button>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-5">
                <div className="rounded-xl border border-blue-200 bg-blue-50 p-4">
                  <h3 className="font-semibold text-blue-800 mb-2">
                    적용되지 않은 문법 태그
                  </h3>

                  {styleApplyResult.missingSyntaxTags.length === 0 ? (
                    <p className="text-sm text-slate-600">
                      저장된 스타일의 문법 태그가 대상 코드에 대부분 반영되어
                      있습니다.
                    </p>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {styleApplyResult.missingSyntaxTags.map((tag, idx) => (
                        <span
                          key={idx}
                          className="px-3 py-1 rounded-full bg-blue-100 text-blue-800 text-sm font-medium"
                        >
                          {tag.tag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                <div className="rounded-xl border border-purple-200 bg-purple-50 p-4">
                  <h3 className="font-semibold text-purple-800 mb-2">
                    적용되지 않은 개념 태그
                  </h3>

                  {styleApplyResult.missingConceptTags.length === 0 ? (
                    <p className="text-sm text-slate-600">
                      저장된 스타일의 구조적 특징이 대상 코드에 대부분 반영되어
                      있습니다.
                    </p>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {styleApplyResult.missingConceptTags.map((tag, idx) => (
                        <span
                          key={idx}
                          className="px-3 py-1 rounded-full bg-purple-100 text-purple-800 text-sm font-medium"
                        >
                          {tag.tag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {styleApplyResult.applyResponse.applied_rules.length > 0 && (
                <div className="rounded-xl border border-green-200 bg-green-50 p-4 mb-5">
                  <h3 className="font-semibold text-green-800 mb-2">
                    실제 적용된 변환 규칙
                  </h3>
                  <ul className="list-disc pl-5 text-sm text-slate-700 space-y-1">
                    {styleApplyResult.applyResponse.applied_rules.map(
                      (rule, idx) => (
                        <li key={idx}>{rule}</li>
                      )
                    )}
                  </ul>
                </div>
              )}

              {styleApplyResult.applyResponse.warnings.length > 0 && (
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
                  <h3 className="font-semibold text-amber-800 mb-2">
                    참고 사항
                  </h3>
                  <ul className="list-disc pl-5 text-sm text-slate-700 space-y-1">
                    {styleApplyResult.applyResponse.warnings.map(
                      (warning, idx) => (
                        <li key={idx}>{warning}</li>
                      )
                    )}
                  </ul>
                </div>
              )}
            </section>
          )}
        </div>
      )}

      {menu === "syntax" && (
        <div className="bg-white border border-slate-300 rounded-2xl p-6 shadow-sm">
          <div className="mb-5">
            <h2 className="text-2xl font-semibold text-slate-900 mb-2">
              문법 태그 목록
            </h2>
            <input
              type="text"
              value={syntaxSearch}
              onChange={(e) => setSyntaxSearch(e.target.value)}
              placeholder="문법 태그 검색..."
              className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-800 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {filteredSyntaxTags.map((item, idx) => (
              <div
                key={idx}
                className="rounded-xl border border-blue-200 bg-blue-50 p-4"
              >
                <div className="inline-block px-3 py-1 rounded-full bg-blue-100 text-blue-800 text-sm font-semibold mb-2">
                  {item.tag}
                </div>
                <p className="text-sm text-slate-700 leading-relaxed">
                  {item.desc}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {menu === "concept" && (
        <div className="bg-white border border-slate-300 rounded-2xl p-6 shadow-sm">
          <div className="mb-5">
            <h2 className="text-2xl font-semibold text-slate-900 mb-2">
              개념 태그 목록
            </h2>
            <input
              type="text"
              value={conceptSearch}
              onChange={(e) => setConceptSearch(e.target.value)}
              placeholder="개념 태그 검색..."
              className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-800 outline-none focus:border-purple-400 focus:ring-2 focus:ring-purple-100"
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {filteredConceptTags.map((item, idx) => (
              <div
                key={idx}
                className="rounded-xl border border-purple-200 bg-purple-50 p-4"
              >
                <div className="inline-block px-3 py-1 rounded-full bg-purple-100 text-purple-800 text-sm font-semibold mb-2">
                  {item.tag}
                </div>
                <p className="text-sm text-slate-700 leading-relaxed">
                  {item.desc}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}