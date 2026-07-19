import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { useAuth } from "@/context/AuthContext";
import { PLAIN_LOGO } from "@/lib/logos";
import { Button } from "@/components/ui/button";
import { Mail, Lock, Eye, EyeOff, Loader2 } from "lucide-react";

export function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email, password);
      await navigate({ to: "/" });
    } catch {
      setError("Invalid email or password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="dark relative flex min-h-screen items-center justify-center bg-[#030712] text-slate-100 px-4 overflow-hidden select-none">
      {/* Immersive space grid and blur spheres */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(255,255,255,0.015)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.015)_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_50%,#000_70%,transparent_100%)] pointer-events-none opacity-40 dark:opacity-100" />
      <div className="absolute top-[-10%] right-[-10%] w-[60%] h-[60%] rounded-full bg-[#a880ff]/10 blur-[130px] pointer-events-none animate-pulse" />
      <div className="absolute bottom-[-10%] left-[-10%] w-[60%] h-[60%] rounded-full bg-[#643f83]/15 blur-[130px] pointer-events-none" />

      <form
        onSubmit={onSubmit}
        className="relative z-10 w-full max-w-md space-y-6 rounded-2xl border border-slate-800/80 bg-slate-900/60 backdrop-blur-xl p-8 shadow-2xl shadow-[#a880ff]/5 transition-all duration-300 hover:shadow-[#a880ff]/10 animate-fade-in-up"
      >
        <div className="space-y-4 text-center">
          <img src={PLAIN_LOGO} alt="SpacePoint" className="mx-auto h-12 w-auto object-contain brightness-110" />
          <div className="space-y-1.5">
            <h1 className="text-2xl font-bold tracking-tight text-white bg-gradient-to-r from-white via-slate-200 to-[#a880ff] bg-clip-text">
              Welcome to SpacePoint
            </h1>
            <p className="text-sm text-slate-400 font-medium">
              Enter your credentials to access the platform
            </p>
          </div>
        </div>

        <div className="space-y-5">
          <div className="space-y-2">
            <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block" htmlFor="email">
              Email Address
            </label>
            <div className="relative group">
              <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500 group-focus-within:text-[#a880ff] transition-colors size-4" />
              <input
                id="email"
                type="email"
                required
                placeholder="name@spacepoint.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full h-11 pl-11 pr-4 rounded-xl border border-slate-800 bg-slate-950/50 hover:bg-slate-950/80 focus:bg-slate-950 text-sm text-white placeholder:text-slate-600 outline-none focus:border-[#a880ff] focus:ring-2 focus:ring-[#a880ff]/20 transition-all"
              />
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block" htmlFor="password">
                Password
              </label>
            </div>
            <div className="relative group">
              <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500 group-focus-within:text-[#a880ff] transition-colors size-4" />
              <input
                id="password"
                type={showPassword ? "text" : "password"}
                required
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full h-11 pl-11 pr-11 rounded-xl border border-slate-800 bg-slate-950/50 hover:bg-slate-950/80 focus:bg-slate-950 text-sm text-white placeholder:text-slate-600 outline-none focus:border-[#a880ff] focus:ring-2 focus:ring-[#a880ff]/20 transition-all"
              />
              <button
                type="button"
                tabIndex={-1}
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 p-1.5 rounded-lg text-slate-500 hover:text-white transition-colors cursor-pointer"
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          <div className="flex items-center justify-between text-xs font-medium py-0.5">
            <label className="flex items-center gap-2 text-slate-400 hover:text-white cursor-pointer transition-colors select-none">
              <input
                type="checkbox"
                className="rounded border-slate-800 bg-slate-950/50 text-[#a880ff] focus:ring-[#a880ff]/20 size-4 transition-all"
              />
              Remember me
            </label>
            <a href="#" className="text-[#a880ff] hover:text-[#a880ff]/80 transition-colors">
              Forgot password?
            </a>
          </div>
        </div>

        {error && (
          <div className="p-3.5 rounded-xl bg-red-950/30 border border-red-900/50 text-red-400 text-xs font-semibold animate-in shake duration-300">
            {error}
          </div>
        )}

        <Button
          type="submit"
          disabled={busy}
          className="w-full h-11 rounded-xl bg-[#a880ff] text-white hover:bg-[#a880ff]/95 text-sm font-semibold tracking-wide shadow-lg shadow-[#a880ff]/10 hover:shadow-[#a880ff]/20 active:scale-[0.98] transition-all duration-200 flex items-center justify-center gap-2"
        >
          {busy ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Signing in…
            </>
          ) : (
            "Sign in"
          )}
        </Button>

        <div className="pt-1 border-t border-slate-800/80 text-center space-y-2.5">
          <p className="pt-3 text-xs font-medium text-slate-400">Don't have an account?</p>
          <div className="flex items-center justify-center gap-x-5 gap-y-1.5 flex-wrap text-xs font-semibold">
            <Link to="/apply/instructor" className="text-[#a880ff] hover:text-[#a880ff]/80 transition-colors">
              Apply as Instructor
            </Link>
            <Link to="/apply/intern" className="text-[#a880ff] hover:text-[#a880ff]/80 transition-colors">
              Apply as Intern
            </Link>
            <Link to="/apply/ambassador" className="text-[#a880ff] hover:text-[#a880ff]/80 transition-colors">
              Apply as Ambassador
            </Link>
          </div>
        </div>
      </form>
    </div>
  );
}
