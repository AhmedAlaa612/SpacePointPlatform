import { useCallback, useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { GraduationCap } from "lucide-react";
import { isAxiosError } from "axios";
import { signup } from "@/api/auth";
import { tokens } from "@/api/client";
import { useAuth } from "@/context/AuthContext";

/**
 * Student signup — mounted on rootRoute, outside the portal auth shell.
 *
 * Posts to `POST /auth/signup` (LM1-4: identity evaluate → find-or-create
 * contact → `User(roles=['student'])` → the same JWT shape /auth/login
 * returns), stores the tokens, and lands on the catalog. A duplicate email
 * comes back as a friendly 409 from the backend.
 */
export default function LearnSignup() {
  const navigate = useNavigate();
  const { setCurrentUser } = useAuth();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setError("");
      setLoading(true);
      try {
        const user = await signup({
          full_name: fullName, email, password,
          phone: phone.trim() ? phone.trim() : undefined,
        });
        setCurrentUser(user);
        void navigate({ to: "/learn" });
      } catch (err) {
        if (isAxiosError(err) && err.response?.status === 409) {
          setError("An account with this email already exists — log in instead.");
        } else {
          setError("Something went wrong. Please try again.");
        }
        tokens.clear();
      } finally {
        setLoading(false);
      }
    },
    [fullName, email, phone, password, setCurrentUser, navigate],
  );

  return (
    <div className="min-h-screen bg-background text-foreground flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="flex items-center justify-center gap-2 mb-8">
          <GraduationCap size={28} className="text-primary" />
          <span className="text-xl font-semibold">Learn</span>
        </div>

        <h1 className="text-center text-lg font-medium mb-6">Sign up</h1>

        {error && (
          <div className="mb-4 p-3 rounded-xl bg-destructive/10 text-destructive text-sm text-center">
            {error}
          </div>
        )}

        <form onSubmit={(e) => void handleSubmit(e)} className="flex flex-col gap-3">
          <input
            type="text"
            placeholder="Full name"
            required
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            className="h-11 px-4 border border-border bg-card rounded-xl text-sm"
          />
          <input
            type="email"
            placeholder="Email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="h-11 px-4 border border-border bg-card rounded-xl text-sm"
          />
          <input
            type="tel"
            placeholder="Phone (optional)"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            className="h-11 px-4 border border-border bg-card rounded-xl text-sm"
          />
          <input
            type="password"
            placeholder="Password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="h-11 px-4 border border-border bg-card rounded-xl text-sm"
          />
          <button
            type="submit"
            disabled={loading}
            className="h-11 bg-primary text-primary-foreground rounded-xl font-medium text-sm disabled:opacity-50 cursor-pointer"
          >
            {loading ? "Signing up..." : "Sign up"}
          </button>
        </form>

        <p className="mt-4 text-center text-sm text-muted-foreground">
          Already have an account?{" "}
          <Link to="/learn/login" className="text-primary font-medium">
            Log in
          </Link>
        </p>
      </div>
    </div>
  );
}
