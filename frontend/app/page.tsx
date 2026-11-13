"use client";

import { useEffect, useState } from "react";

import AnalyzeSection from "../components/sections/AnalyzeSection";
import LoginSection from "../components/sections/LoginSection";
import StyleSection from "../components/sections/StyleSection";
import StyleApplySection from "../components/sections/StyleApplySection";
import SyntaxTagSection from "../components/sections/SyntaxTagSection";
import ConceptTagSection from "../components/sections/ConceptTagSection";

import { useCodeAnalysis } from "../hooks/useCodeAnalysis";
import { useCodingStyles } from "../hooks/useCodingStyles";
import { useStyleApplication } from "../hooks/useStyleApplication";
import { useTagSearch } from "../hooks/useTagSearch";

type MenuType =
  | "analyze"
  | "login"
  | "style"
  | "styleApply"
  | "syntax"
  | "concept";

const isMenuType = (value: string): value is MenuType =>
  ["analyze", "login", "style", "styleApply", "syntax", "concept"].includes(
    value
  );

export default function HomePage() {
  const [menu, setMenu] = useState<MenuType>("analyze");

  const styles = useCodingStyles();
  const analysis = useCodeAnalysis(styles.savedStyles.length);
  const application = useStyleApplication(styles.savedStyles);
  const tagSearch = useTagSearch();

  useEffect(() => {
    const syncMenuWithHash = () => {
      const hashValue = window.location.hash.replace("#", "");
      if (isMenuType(hashValue)) setMenu(hashValue);
    };

    syncMenuWithHash();
    window.addEventListener("hashchange", syncMenuWithHash);
    return () => window.removeEventListener("hashchange", syncMenuWithHash);
  }, []);

  const handleSaveStyle = () => {
    if (!analysis.stylePreview) {
      alert("저장할 분석 결과가 없습니다.");
      return;
    }
    if (styles.saveCodingStyle(analysis.stylePreview)) {
      analysis.prepareNextStyle();
    }
  };

  const handleLogin = () => {
    if (styles.handleLogin()) application.resetSelection();
  };

  const handleLogout = () => {
    styles.handleLogout();
    application.resetSelection();
  };

  const handleDeleteStyle = (id: string) => {
    if (styles.handleDeleteStyle(id)) {
      application.clearDeletedSelection(id);
    }
  };

  return (
    <>
      {menu === "analyze" && (
        <AnalyzeSection
          code={analysis.code}
          setCode={analysis.setCode}
          loading={analysis.loading}
          handleAnalyze={analysis.handleAnalyze}
          result={analysis.result}
          styleName={analysis.styleName}
          setStyleName={analysis.setStyleName}
          handleSaveStyle={handleSaveStyle}
          stylePreview={analysis.stylePreview}
        />
      )}

      {menu === "login" && (
        <LoginSection
          currentUser={styles.currentUser}
          loginEmail={styles.loginEmail}
          setLoginEmail={styles.setLoginEmail}
          loginPassword={styles.loginPassword}
          setLoginPassword={styles.setLoginPassword}
          handleLogin={handleLogin}
          handleLogout={handleLogout}
        />
      )}

      {menu === "style" && (
        <StyleSection
          currentUser={styles.currentUser}
          savedStyles={styles.savedStyles}
          shareModalStyle={styles.shareModalStyle}
          shareTargetEmail={styles.shareTargetEmail}
          setShareTargetEmail={styles.setShareTargetEmail}
          setShareModalStyle={styles.setShareModalStyle}
          handleOpenShareModal={styles.handleOpenShareModal}
          handleDeleteStyle={handleDeleteStyle}
          handleShareStyle={styles.handleShareStyle}
        />
      )}

      {menu === "styleApply" && (
        <StyleApplySection
          selectedStyleId={application.selectedStyleId}
          setSelectedStyleId={application.setSelectedStyleId}
          savedStyles={styles.savedStyles}
          selectedStyle={application.selectedStyle}
          targetCode={application.targetCode}
          setTargetCode={application.setTargetCode}
          handleApplyStyle={application.handleApplyStyle}
          styleApplyLoading={application.styleApplyLoading}
          styleApplyResult={application.styleApplyResult}
          setStyleApplyResult={application.setStyleApplyResult}
          editableTransformedCode={application.editableTransformedCode}
          setEditableTransformedCode={application.setEditableTransformedCode}
        />
      )}

      {menu === "syntax" && (
        <SyntaxTagSection
          syntaxSearch={tagSearch.syntaxSearch}
          setSyntaxSearch={tagSearch.setSyntaxSearch}
          filteredSyntaxTags={tagSearch.filteredSyntaxTags}
        />
      )}

      {menu === "concept" && (
        <ConceptTagSection
          conceptSearch={tagSearch.conceptSearch}
          setConceptSearch={tagSearch.setConceptSearch}
          filteredConceptTags={tagSearch.filteredConceptTags}
        />
      )}
    </>
  );
}
