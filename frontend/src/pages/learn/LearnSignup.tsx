import { useCallback, useState } from "react";
import { Link } from "@tanstack/react-router";
import { GraduationCap } from "lucide-react";

/**
 * Student signup — mounted on rootRoute, outside the portal auth shell.
 *
 * LM1-4 implements the actual signup endpoint (`POST /auth/signup` →
 * `resolve_or_create_contact` → `User(roles=['student'])` → JWT), at which
 * point this posts the form and navigates to /learn on success. Until then the
 * form renders and validates but has nowhere to submit.
 */
export default function LearnSignup() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    // LM1-4 wires POST /auth/signup here.
    setError("Signup isn't live yet — ask ops to create your account for now.");
  }, []);

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

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
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
            className="h-11 bg-primary text-primary-foreground rounded-xl font-medium text-sm cursor-pointer"
          >
            Sign up
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
