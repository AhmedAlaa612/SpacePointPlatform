import { useCallback, useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { ChevronDown } from "lucide-react";
import { isAxiosError } from "axios";
import { signup } from "@/api/auth";
import { tokens } from "@/api/client";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { CountrySelect } from "@/components/ui/CountrySelect";
import { CitySelect, useCitiesForCountry } from "@/components/ui/CitySelect";
import { DomainIcon } from "@/components/ui/DomainIcon";

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
  const [dob, setDob] = useState("");
  const [country, setCountry] = useState("");
  const [cityId, setCityId] = useState("");
  const [cityOther, setCityOther] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [parentOpen, setParentOpen] = useState(false);
  const [parentName, setParentName] = useState("");
  const [parentPhone, setParentPhone] = useState("");
  const [parentEmail, setParentEmail] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const countryCities = useCitiesForCountry(country);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setError("");
      setLoading(true);
      try {
        const user = await signup({
          full_name: fullName, email, password,
          phone: phone.trim() ? phone.trim() : undefined,
          date_of_birth: dob || undefined,
          country: country || undefined,
          city_id: cityId || undefined,
          city_other: cityOther || undefined,
          invite_code: inviteCode.trim(),
          ...(parentName.trim() && parentPhone.trim()
            ? { parent_name: parentName.trim(), parent_phone: parentPhone.trim(), parent_email: parentEmail.trim() || undefined }
            : {}),
        });
        setCurrentUser(user);
        void navigate({ to: "/learn" });
      } catch (err) {
        if (isAxiosError(err) && err.response?.status === 409) {
          setError("An account with this email already exists — log in instead.");
        } else if (isAxiosError(err) && err.response?.status === 400) {
          const detail = err.response.data?.detail;
          setError(typeof detail === "string" ? detail : "Something went wrong. Please try again.");
        } else {
          setError("Something went wrong. Please try again.");
        }
        tokens.clear();
      } finally {
        setLoading(false);
      }
    },
    [fullName, email, phone, password, dob, country, cityId, cityOther, inviteCode, parentName, parentPhone, parentEmail, setCurrentUser, navigate],
  );

  return (
    <div className="min-h-screen bg-background text-foreground flex items-center justify-center px-4 bg-[radial-gradient(circle_at_15%_10%,hsl(var(--primary)/0.06)_0%,transparent_45%)]">
      <div className="w-full max-w-sm">
        <div className="flex justify-center mb-8">
          <DomainIcon className="h-10 w-auto" />
        </div>

        <Card className="p-6 sm:p-7">
          <h1 className="text-center font-display text-xl font-bold mb-6">Sign up</h1>

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
              className="h-11 px-4 rounded-xl text-sm bg-background ring-1 ring-border focus:outline-none focus:ring-primary/50 transition-shadow"
            />
            <input
              type="email"
              placeholder="Email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="h-11 px-4 rounded-xl text-sm bg-background ring-1 ring-border focus:outline-none focus:ring-primary/50 transition-shadow"
            />
            <input
              type="tel"
              placeholder="Phone (optional)"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="h-11 px-4 rounded-xl text-sm bg-background ring-1 ring-border focus:outline-none focus:ring-primary/50 transition-shadow"
            />
            <div>
              <label className="block text-[11px] text-muted-foreground mb-1 pl-0.5">Date of birth (optional)</label>
              <input
                type="date"
                value={dob}
                onChange={(e) => setDob(e.target.value)}
                className="w-full h-11 px-4 rounded-xl text-sm bg-background ring-1 ring-border focus:outline-none focus:ring-primary/50 transition-shadow"
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-[11px] text-muted-foreground mb-1 pl-0.5">Country (optional)</label>
                <CountrySelect
                  value={country}
                  onChange={setCountry}
                  valueType="code"
                  className="w-full h-11 px-4 rounded-xl text-sm bg-background ring-1 ring-border focus:outline-none focus:ring-primary/50 transition-shadow"
                />
              </div>
              {countryCities.length > 0 || country ? (
                <div>
                  <label className="block text-[11px] text-muted-foreground mb-1 pl-0.5">
                    City <span className="normal-case font-normal">(optional)</span>
                  </label>
                  <CitySelect
                    country={country}
                    value={cityId}
                    onChange={setCityId}
                    otherValue={cityOther}
                    onOtherChange={setCityOther}
                    className="w-full h-11 px-4 rounded-xl text-sm bg-background ring-1 ring-border focus:outline-none focus:ring-primary/50 transition-shadow"
                  />
                </div>
              ) : null}
            </div>
            {/* Required as of 2026-08-13 — signup is invite-only. Ask your
                instructor/school for the batch code. */}
            <div className="flex flex-col gap-1">
              <input
                type="text"
                placeholder="Invite code"
                required
                value={inviteCode}
                onChange={(e) => setInviteCode(e.target.value.toUpperCase())}
                className="h-11 px-4 rounded-xl text-sm bg-background ring-1 ring-border focus:outline-none focus:ring-primary/50 transition-shadow font-mono"
              />
              <span className="text-xs text-muted-foreground px-1">
                Ask your instructor for your class's invite code.
              </span>
            </div>
            <input
              type="password"
              placeholder="Password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="h-11 px-4 rounded-xl text-sm bg-background ring-1 ring-border focus:outline-none focus:ring-primary/50 transition-shadow"
            />

            <button
              type="button" onClick={() => setParentOpen((v) => !v)}
              className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors w-fit cursor-pointer"
            >
              <ChevronDown className={`size-3.5 transition-transform ${parentOpen ? "rotate-180" : ""}`} />
              Parent/guardian information (optional)
            </button>
            {parentOpen && (
              <div className="flex flex-col gap-2 pl-3 border-l-2 border-border ml-1">
                <input
                  type="text" placeholder="Parent/guardian name"
                  value={parentName} onChange={(e) => setParentName(e.target.value)}
                  className="h-10 px-3.5 rounded-xl text-sm bg-background ring-1 ring-border focus:outline-none focus:ring-primary/50 transition-shadow"
                />
                <input
                  type="tel" placeholder="Parent/guardian phone"
                  value={parentPhone} onChange={(e) => setParentPhone(e.target.value)}
                  className="h-10 px-3.5 rounded-xl text-sm bg-background ring-1 ring-border focus:outline-none focus:ring-primary/50 transition-shadow"
                />
                <input
                  type="email" placeholder="Parent/guardian email (optional)"
                  value={parentEmail} onChange={(e) => setParentEmail(e.target.value)}
                  className="h-10 px-3.5 rounded-xl text-sm bg-background ring-1 ring-border focus:outline-none focus:ring-primary/50 transition-shadow"
                />
              </div>
            )}

            <Button size="xl" type="submit" disabled={loading || !inviteCode.trim()} className="w-full mt-1">
              {loading ? "Signing up..." : "Sign up"}
            </Button>
          </form>
        </Card>

        <p className="mt-5 text-center text-sm text-muted-foreground">
          Already have an account?{" "}
          <Link to="/learn/login" className="text-primary font-medium">
            Log in
          </Link>
        </p>
      </div>
    </div>
  );
}
