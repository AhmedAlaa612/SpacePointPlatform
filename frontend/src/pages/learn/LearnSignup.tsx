import { useCallback, useState } from "react";
import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { ChevronDown, Ticket } from "lucide-react";
import { isAxiosError } from "axios";
import { signup } from "@/api/auth";
import { tokens } from "@/api/client";
import { FinWidget } from "@/components/FinWidget";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { CountrySelect } from "@/components/ui/CountrySelect";
import { CitySelect, useCitiesForCountry } from "@/components/ui/CitySelect";
import { DomainIcon } from "@/components/ui/DomainIcon";
import { PasswordInput } from "@/components/ui/PasswordInput";
import { resolveLearnLanding } from "./resolveLearnLanding";

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
  const search = useSearch({ strict: false }) as { invite?: string; code?: string };
  const urlInvite = (search.invite ?? search.code ?? "").trim().toUpperCase();
  const { setCurrentUser } = useAuth();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [dob, setDob] = useState("");
  const [country, setCountry] = useState("");
  const [cityId, setCityId] = useState("");
  const [cityOther, setCityOther] = useState("");
  const [inviteCode, setInviteCode] = useState(urlInvite);
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
          phone: phone.trim(),
          date_of_birth: dob || undefined,
          country: country || undefined,
          city_id: cityId || undefined,
          city_other: cityOther || undefined,
          invite_code: inviteCode.trim() || undefined,
          ...(parentName.trim() && parentPhone.trim()
            ? { parent_name: parentName.trim(), parent_phone: parentPhone.trim(), parent_email: parentEmail.trim() || undefined }
            : {}),
        });
        setCurrentUser(user);
        void navigate({ to: await resolveLearnLanding() });
      } catch (err) {
        if (isAxiosError(err)) {
          if (err.response?.status === 409) {
            setError("An account with this email already exists — log in instead.");
          } else if (err.response?.status === 400 || err.response?.status === 422) {
            const detail = err.response.data?.detail;
            if (typeof detail === "string") {
              setError(detail);
            } else if (Array.isArray(detail) && detail.length > 0) {
              const first = detail[0];
              const field = first?.loc?.[first.loc.length - 1];
              const msg = first?.msg || "Invalid input";
              setError(field && field !== "body" ? `${field}: ${msg}` : msg);
            } else {
              setError("Please check your input and try again.");
            }
          } else {
            const detail = err.response?.data?.detail;
            setError(typeof detail === "string" ? detail : "Something went wrong. Please try again.");
          }
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
    <div className="min-h-screen bg-background dark:bg-[#05030A] text-foreground flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm">
        <div className="flex justify-center mb-8">
          <DomainIcon className="h-10 w-auto" />
        </div>

        <div className="lms-card p-6 sm:p-8 rounded-2xl shadow-2xl">
          <h1 className="text-center font-['Outfit'] text-2xl font-bold mb-6 text-foreground">Sign up</h1>

          {error && (
            <div className="mb-4 p-3 rounded-xl bg-destructive/10 border border-destructive/20 text-destructive text-sm text-center">
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
              className="lms-input h-11 px-4 text-sm w-full"
            />
            <input
              type="email"
              placeholder="Email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="lms-input h-11 px-4 text-sm w-full"
            />
            <input
              type="tel"
              placeholder="Phone"
              required
              maxLength={20}
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="lms-input h-11 px-4 text-sm w-full"
            />
            <div>
              <label className="block text-[11px] text-muted-foreground mb-1 pl-0.5">Date of birth (optional)</label>
              <input
                type="date"
                value={dob}
                onChange={(e) => setDob(e.target.value)}
                className="lms-input w-full h-11 px-4 text-sm"
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-[11px] text-muted-foreground mb-1 pl-0.5">Country (optional)</label>
                <CountrySelect
                  value={country}
                  onChange={setCountry}
                  valueType="code"
                  className="lms-input w-full h-11 px-4 text-sm"
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
                    className="lms-input w-full h-11 px-4 text-sm"
                  />
                </div>
              ) : null}
            </div>
            <div className="flex flex-col gap-1">
              {urlInvite && inviteCode === urlInvite && (
                <div className="flex items-center gap-1.5 text-xs font-medium text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-1 rounded-lg w-fit mb-0.5">
                  <Ticket className="size-3.5" />
                  Invite code {urlInvite} applied
                </div>
              )}
              <input
                type="text"
                placeholder="Invite code"
                value={inviteCode}
                onChange={(e) => setInviteCode(e.target.value.toUpperCase())}
                className="lms-input h-11 px-4 text-sm w-full font-mono"
              />
              <span className="text-xs text-muted-foreground px-1">
                Enter your class invite code if given one.
              </span>
            </div>
            <PasswordInput
              placeholder="Password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="lms-input h-11 px-4 text-sm w-full"
            />

            <button
              type="button" onClick={() => setParentOpen((v) => !v)}
              className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors w-fit cursor-pointer"
            >
              <ChevronDown className={`size-3.5 transition-transform ${parentOpen ? "rotate-180" : ""}`} />
              Parent/guardian information (optional)
            </button>
            {parentOpen && (
              <div className="flex flex-col gap-2 pl-3 border-l-2 border-lms-cta-border dark:border-lms-accent-border ml-1">
                <input
                  type="text" placeholder="Parent/guardian name"
                  value={parentName} onChange={(e) => setParentName(e.target.value)}
                  className="lms-input h-10 px-3.5 text-sm"
                />
                <input
                  type="tel" placeholder="Parent/guardian phone"
                  maxLength={20}
                  value={parentPhone} onChange={(e) => setParentPhone(e.target.value)}
                  className="lms-input h-10 px-3.5 text-sm"
                />
                <input
                  type="email" placeholder="Parent/guardian email (optional)"
                  value={parentEmail} onChange={(e) => setParentEmail(e.target.value)}
                  className="lms-input h-10 px-3.5 text-sm"
                />
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="lms-btn-primary w-full h-11 text-sm font-bold rounded-xl mt-1 flex items-center justify-center cursor-pointer disabled:opacity-50"
            >
              {loading ? "Signing up..." : "Sign up"}
            </button>
          </form>
        </div>

        <p className="mt-5 text-center text-sm text-muted-foreground">
          Already have an account?{" "}
          <Link
            to="/learn/login"
            search={inviteCode.trim() ? { invite: inviteCode.trim().toUpperCase() } : undefined}
            className="lms-link"
          >
            Log in
          </Link>
        </p>
      </div>
      <FinWidget />
    </div>
  );
}
