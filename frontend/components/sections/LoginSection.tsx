interface AuthUser {
  email: string;
}

interface LoginSectionProps {
  currentUser: AuthUser | null;
  loginEmail: string;
  setLoginEmail: (value: string) => void;
  loginPassword: string;
  setLoginPassword: (value: string) => void;
  handleLogin: () => void;
  handleLogout: () => void;
}

export default function LoginSection({
  currentUser,
  loginEmail,
  setLoginEmail,
  loginPassword,
  setLoginPassword,
  handleLogin,
  handleLogout,
}: LoginSectionProps) {
  return (
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
            테스트용 계정으로 로그인하면 계정별 코딩 스타일 저장 목록과 공유
            기능을 사용할 수 있습니다.
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
  );
}