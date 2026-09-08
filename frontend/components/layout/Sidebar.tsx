"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const menuItems = [
  { label: "로그인", href: "/login", disabled: true },
  { label: "스타일 목록", href: "/styles", disabled: true },
  { label: "문법 태그 목록", href: "/syntax-tags" },
  { label: "개념 태그 목록", href: "/concept-tags" },
  { label: "분석 화면", href: "/" },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-full xl:w-[240px] shrink-0">
      <div className="rounded-2xl border border-slate-300 bg-white p-4 shadow-sm">
        <h2 className="text-2xl font-bold text-slate-900 mb-6">메뉴</h2>

        <div className="space-y-3">
          {menuItems.map((item) => {
            const isActive = pathname === item.href;

            if (item.disabled) {
              return (
                <div
                  key={item.label}
                  className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-400 cursor-not-allowed"
                >
                  {item.label}
                </div>
              );
            }

            return (
              <Link
                key={item.label}
                href={item.href}
                className={`block w-full rounded-xl border px-4 py-3 transition ${
                  isActive
                    ? "bg-slate-900 text-white border-slate-900"
                    : "bg-white text-slate-700 border-slate-300 hover:bg-slate-100"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </div>

        <div className="mt-6 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600 leading-relaxed">
          현재는 Python 코드만 지원하며, AST 기반 분석 엔진을 통해 문법 요소와 구조적 특징을 분석합니다.
        </div>
      </div>
    </aside>
  );
}