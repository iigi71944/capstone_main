
"use client";

import { useState } from "react";
import type { CodingStyle } from "../../types/analysis";

interface AuthUser {
  email: string;
}

type SharedCodingStyle = CodingStyle & {
  is_shared?: boolean;
  shared_from?: string;
  shared_at?: string;
};

interface StyleSectionProps {
  currentUser: AuthUser | null;
  savedStyles: SharedCodingStyle[];
  shareModalStyle: SharedCodingStyle | null;
  shareTargetEmail: string;
  setShareTargetEmail: (value: string) => void;
  setShareModalStyle: (style: SharedCodingStyle | null) => void;
  handleOpenShareModal: (style: SharedCodingStyle) => void;
  handleDeleteStyle: (styleId: string) => void;
  handleShareStyle: () => void;
}

export default function StyleSection({
  currentUser,
  savedStyles,
  shareModalStyle,
  shareTargetEmail,
  setShareTargetEmail,
  setShareModalStyle,
  handleOpenShareModal,
  handleDeleteStyle,
  handleShareStyle,
}: StyleSectionProps) {
  // 삭제 확인을 기다리는 스타일
  const [deleteTarget, setDeleteTarget] =
    useState<SharedCodingStyle | null>(null);

  // 삭제 버튼을 누르면 확인 팝업만 표시합니다.
  const openDeleteModal = (style: SharedCodingStyle) => {
    setDeleteTarget(style);
  };

  // 아니오: 삭제하지 않고 팝업을 닫습니다.
  const cancelDelete = () => {
    setDeleteTarget(null);
  };

  // 삭제: 기존 삭제 함수를 실행합니다.
  const confirmDelete = () => {
    if (!deleteTarget) {
      return;
    }

    handleDeleteStyle(deleteTarget.id);
    setDeleteTarget(null);
  };

  return (
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
            현재 계정:{" "}
            {currentUser
              ? currentUser.email
              : "비로그인 임시 저장소"}
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
                      type="button"
                      onClick={() => handleOpenShareModal(style)}
                      className="text-xs px-3 py-1 rounded-lg border border-blue-200 text-blue-700 bg-white hover:bg-blue-50"
                    >
                      공유
                    </button>

                    <button
                      type="button"
                      onClick={() => openDeleteModal(style)}
                      className="text-xs px-3 py-1 rounded-lg border border-red-200 text-red-600 bg-white hover:bg-red-50"
                    >
                      삭제
                    </button>
                  </div>
                </div>

                {/*
                  코딩 스타일 설명 영역

                  변경 전:
                  line-clamp-3

                  변경 후:
                  max-h-24 overflow-y-auto

                  내용이 길면 이 영역 안에서만
                  세로 스크롤이 가능해집니다.
                  저장된 설명은 생략하지 않습니다.
                */}
                <p
                  tabIndex={0}
                  aria-label={`${style.name} 코딩 스타일 설명`}
                  className="text-sm text-slate-700 leading-relaxed mb-4 max-h-24 overflow-y-auto overscroll-contain whitespace-pre-wrap break-words pr-2"
                >
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

      {/* 기존 코딩 스타일 공유 팝업 */}
      {shareModalStyle && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="share-modal-title"
            className="w-full max-w-md rounded-2xl bg-white border border-slate-300 p-5 shadow-xl"
          >
            <h3
              id="share-modal-title"
              className="text-lg font-semibold text-slate-900 mb-2"
            >
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
                현재 공유 가능 계정: test001@gmail.com,
                test002@gmail.com
              </p>
            </div>

            <input
              type="email"
              value={shareTargetEmail}
              onChange={(e) =>
                setShareTargetEmail(e.target.value)
              }
              placeholder="공유할 계정 이메일"
              className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none focus:border-slate-500 mb-4"
            />

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setShareModalStyle(null);
                  setShareTargetEmail("");
                }}
                className="px-4 py-2 rounded-xl border border-slate-300 text-slate-700 hover:bg-slate-50"
              >
                취소
              </button>

              <button
                type="button"
                onClick={handleShareStyle}
                className="px-4 py-2 rounded-xl bg-slate-900 text-white hover:bg-slate-700"
              >
                공유하기
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 기존 코딩 스타일 삭제 확인 팝업 */}
      {deleteTarget && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 px-4">
          <div
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="delete-modal-title"
            aria-describedby="delete-modal-description"
            className="w-full max-w-md rounded-2xl border border-slate-300 bg-white p-6 shadow-xl"
          >
            <h3
              id="delete-modal-title"
              className="text-lg font-semibold text-slate-900"
            >
              코딩 스타일 삭제
            </h3>

            <p className="mt-4 text-base font-semibold text-slate-900">
              정말로 삭제하시겠습니까?
            </p>

            <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-medium text-slate-500">
                삭제할 코딩 스타일
              </p>

              <p className="mt-1 break-words text-sm font-semibold text-slate-900">
                {deleteTarget.name}
              </p>
            </div>

            <p
              id="delete-modal-description"
              className="mt-4 text-sm leading-relaxed text-slate-600"
            >
              선택한 코딩 스타일이 삭제됩니다.
              삭제 후에는 복구할 수 없습니다.
            </p>

            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                onClick={cancelDelete}
                className="rounded-xl border border-slate-300 bg-white px-5 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
              >
                아니오
              </button>

              <button
                type="button"
                onClick={confirmDelete}
                className="rounded-xl bg-red-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-300"
              >
                삭제
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
