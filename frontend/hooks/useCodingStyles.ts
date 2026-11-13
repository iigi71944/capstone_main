"use client";

import { useEffect, useState } from "react";
import { createCodingStyleId } from "../lib/codingStyleFactory";
import type { CodingStyle, ConceptTag } from "../types/analysis";

export interface AuthUser {
  email: string;
}

export type SharedCodingStyle = CodingStyle & {
  is_shared?: boolean;
  shared_from?: string;
  shared_at?: string;
};

const GUEST_EMAIL = "guest";
const STORAGE_KEY_PREFIX = "capstone_saved_coding_styles";
const CURRENT_USER_STORAGE_KEY = "capstone_current_user";
const MIGRATION_BACKUP_SUFFIX = "_backup_before_tag_migration_v1";
const LEGACY_INDEX_LOOP_TAG = "반복 인덱스 개선 가능 구조";
const INDEX_LOOP_STYLE_TAG = "인덱스 기반 반복 사용";

const REMOVED_DIAGNOSTIC_TAGS = new Set([
  "간결성 저하 가능 구조",
  "구조화 필요 코드",
  "중복 로직 포함 구조",
]);

const TEST_ACCOUNTS = [
  { email: "test001@gmail.com", password: "12090" },
  { email: "test002@gmail.com", password: "12090" },
];

const getStyleStorageKey = (email: string) =>
  `${STORAGE_KEY_PREFIX}_${email}`;

function migrateSavedStyle(style: SharedCodingStyle): SharedCodingStyle {
  const originalTags = Array.isArray(style.concept_tags)
    ? style.concept_tags
    : [];

  const needsMigration = originalTags.some(
    (item) =>
      item?.tag === LEGACY_INDEX_LOOP_TAG ||
      REMOVED_DIAGNOSTIC_TAGS.has(item?.tag)
  );
  if (!needsMigration) return style;

  const hasCurrentIndexTag = originalTags.some(
    (item) => item?.tag === INDEX_LOOP_STYLE_TAG
  );
  const seenTags = new Set<string>();
  const migratedTags: ConceptTag[] = [];

  for (const item of originalTags) {
    if (!item || typeof item.tag !== "string") continue;
    if (REMOVED_DIAGNOSTIC_TAGS.has(item.tag)) continue;

    if (item.tag === LEGACY_INDEX_LOOP_TAG) {
      if (hasCurrentIndexTag || seenTags.has(INDEX_LOOP_STYLE_TAG)) {
        continue;
      }
      migratedTags.push({
        tag: INDEX_LOOP_STYLE_TAG,
        count: item.count,
        score: item.score,
      });
      seenTags.add(INDEX_LOOP_STYLE_TAG);
      continue;
    }

    if (!seenTags.has(item.tag)) {
      migratedTags.push(item);
      seenTags.add(item.tag);
    }
  }

  let migratedDescription = style.description;
  if (
    typeof style.description === "string" &&
    style.description.startsWith("이 코딩 스타일은 개념 태그(")
  ) {
    const conceptNames =
      migratedTags.map((item) => item.tag).join(", ") ||
      "특정 개념 태그 없음";
    const syntaxNames =
      (style.syntax_tags ?? []).map((item) => item.tag).join(", ") ||
      "저장 대상 핵심 문법 태그 없음";
    migratedDescription =
      `이 코딩 스타일은 개념 태그(${conceptNames})를 코드 구조 기준으로 사용하고, ` +
      `저장용 핵심 문법 태그(${syntaxNames})를 적용 가능한 문법 한계로 사용한다.`;
  }

  return {
    ...style,
    concept_tags: migratedTags,
    description: migratedDescription,
  };
}

export function useCodingStyles() {
  const [savedStyles, setSavedStyles] = useState<SharedCodingStyle[]>([]);
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [shareTargetEmail, setShareTargetEmail] = useState("");
  const [shareModalStyle, setShareModalStyle] =
    useState<SharedCodingStyle | null>(null);

  const loadStylesByEmail = (email: string) => {
    const storageKey = getStyleStorageKey(email);
    const raw = localStorage.getItem(storageKey);
    if (!raw) {
      setSavedStyles([]);
      return;
    }

    try {
      const parsed: unknown = JSON.parse(raw);
      if (
        !Array.isArray(parsed) ||
        !parsed.every((item) => item && typeof item === "object")
      ) {
        console.error("저장된 코딩 스타일의 데이터 형식이 올바르지 않습니다.");
        setSavedStyles([]);
        return;
      }

      const originalStyles = parsed as SharedCodingStyle[];
      const migratedStyles = originalStyles.map(migrateSavedStyle);
      const hasMigration = migratedStyles.some(
        (style, index) => style !== originalStyles[index]
      );

      if (hasMigration) {
        try {
          const backupKey = `${storageKey}${MIGRATION_BACKUP_SUFFIX}`;
          if (localStorage.getItem(backupKey) === null) {
            localStorage.setItem(backupKey, raw);
          }
          localStorage.setItem(storageKey, JSON.stringify(migratedStyles));
        } catch (error) {
          console.error("코딩 스타일 이전 데이터 저장에 실패했습니다:", error);
        }
      }
      setSavedStyles(migratedStyles);
    } catch (error) {
      console.error("저장된 코딩 스타일을 읽을 수 없습니다:", error);
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

  const saveStylesToStorage = (styles: SharedCodingStyle[]): boolean => {
    const email = currentUser?.email || GUEST_EMAIL;
    const storageKey = getStyleStorageKey(email);
    try {
      localStorage.setItem(storageKey, JSON.stringify(styles));
      setSavedStyles(styles);
      return true;
    } catch (error) {
      console.error("코딩 스타일 저장 오류:", error);
      alert("브라우저 저장소에 코딩 스타일을 저장하지 못했습니다.");
      return false;
    }
  };

  const saveCodingStyle = (style: SharedCodingStyle): boolean => {
    const saved = saveStylesToStorage([style, ...savedStyles]);
    if (saved) alert("코딩 스타일이 저장되었습니다.");
    return saved;
  };

  const handleDeleteStyle = (id: string): boolean =>
    saveStylesToStorage(savedStyles.filter((style) => style.id !== id));

  const handleLogin = (): boolean => {
    const account = TEST_ACCOUNTS.find(
      (item) =>
        item.email === loginEmail.trim() &&
        item.password === loginPassword
    );
    if (!account) {
      alert("이메일 또는 비밀번호가 올바르지 않습니다.");
      return false;
    }

    const nextUser: AuthUser = { email: account.email };
    setCurrentUser(nextUser);
    localStorage.setItem(CURRENT_USER_STORAGE_KEY, JSON.stringify(nextUser));
    loadStylesByEmail(account.email);
    setLoginEmail("");
    setLoginPassword("");
    alert(`${account.email} 계정으로 로그인되었습니다.`);
    return true;
  };

  const handleLogout = () => {
    setCurrentUser(null);
    localStorage.removeItem(CURRENT_USER_STORAGE_KEY);
    loadStylesByEmail(GUEST_EMAIL);
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
    if (!TEST_ACCOUNTS.some((account) => account.email === targetEmail)) {
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
      id: createCodingStyleId(),
      name: shareModalStyle.name,
      is_shared: true,
      shared_from: currentUser.email,
      shared_at: new Date().toLocaleString(),
      created_at: new Date().toLocaleString(),
    };

    try {
      localStorage.setItem(
        targetStorageKey,
        JSON.stringify([sharedStyle, ...targetStyles])
      );
    } catch (error) {
      console.error("코딩 스타일 공유 오류:", error);
      alert("코딩 스타일 공유 정보를 저장하지 못했습니다.");
      return;
    }

    setShareModalStyle(null);
    setShareTargetEmail("");
    alert(`${targetEmail} 계정으로 코딩 스타일을 공유했습니다.`);
  };

  return {
    savedStyles,
    currentUser,
    loginEmail,
    setLoginEmail,
    loginPassword,
    setLoginPassword,
    shareTargetEmail,
    setShareTargetEmail,
    shareModalStyle,
    setShareModalStyle,
    saveCodingStyle,
    handleDeleteStyle,
    handleLogin,
    handleLogout,
    handleOpenShareModal,
    handleShareStyle,
  };
}
