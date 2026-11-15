import { useCallback, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { ChevronDown, Ticket } from "lucide-react";
import { isAxiosError } from "axios";
import { getPublicFormConfigApi } from "@/api/apply";
import { signup } from "@/api/auth";
import { tokens } from "@/api/client";
import {
  CustomQuestionsFields,
  isFieldEnabled,
  isFieldRequired,
  validateCustomQuestionAnswers,
} from "@/components/apply/CustomQuestionsFields";
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
  const [nationality, setNationality] = useState("");
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
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const { data: formConfig } = useQuery({
    queryKey: ["apply-form-config", "student"],
    queryFn: () => getPublicFormConfigApi("student"),
  });

  const fields = formConfig?.fields;
  const questions = formConfig?.questions ?? [];
  const phoneEnabled = isFieldEnabled(fields, "phone", true);
  const phoneRequired = isFieldRequired(fields, "phone", true);
  const nationalityEnabled = isFieldEnabled(fields, "nationality", true);
  const nationalityRequired = isFieldRequired(fields, "nationality", true);
  const dobEnabled = isFieldEnabled(fields, "date_of_birth", true);
  const dobRequired = isFieldRequired(fields, "date_of_birth", false);
  const countryEnabled = isFieldEnabled(fields, "country", true);
  const countryRequired = isFieldRequired(fields, "country", false);
  const cityEnabled = isFieldEnabled(fields, "city", true);
  const cityRequired = isFieldRequired(fields, "city", false);
  const inviteEnabled = isFieldEnabled(fields, "invite_code", true);
  const inviteRequired = isFieldRequired(fields, "invite_code", false);
  const parentEnabled = isFieldEnabled(fields, "parent_info", true);
  const parentRequired = isFieldRequired(fields, "parent_info", false);

  const countryCities = useCitiesForCountry(country);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setError("");
      if (phoneRequired && !phone.trim()) {
        setError("Phone number is required.");
        return;
      }
      if (nationalityRequired && !nationality) {
        setError("Nationality is required.");
        return;
      }
      if (dobRequired && !dob) {
        setError("Date of birth is required.");
        return;
      }
      if (countryRequired && !country) {
        setError("Country is required.");
        return;
      }
      if (cityRequired && country && !cityId && !cityOther.trim()) {
        setError("City is required.");
        return;
      }
      if (inviteRequired && !inviteCode.trim()) {
        setError("Invite code is required.");
        return;
      }
      if (parentRequired && (!parentName.trim() || !parentPhone.trim())) {
        setError("Parent/guardian name and phone are required.");
        return;
      }
      const qErr = validateCustomQuestionAnswers(questions, answers);
      if (qErr) {
        setError(qErr);
        return;
      }
      setLoading(true);
      try {
        const user = await signup({
          full_name: fullName, email, password,
          phone: phone.trim() || undefined,
          nationality: nationality || undefined,
          date_of_birth: dob || undefined,
          country: country || undefined,
          city_id: cityId || undefined,
          city_other: cityOther || undefined,
          invite_code: inviteCode.trim() || undefined,
          ...(parentName.trim() && parentPhone.trim()
            ? { parent_name: parentName.trim(), parent_phone: parentPhone.trim(), parent_email: parentEmail.trim() || undefined }
            : {}),
          answers: Object.keys(answers).length > 0 ? answers : undefined,
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
    [fullName, email, phone, phoneRequired, nationality, nationalityRequired, password, dob, dobRequired, country, countryRequired, cityId, cityOther, cityRequired, inviteCode, inviteRequired, parentName, parentPhone, parentEmail, parentRequired, questions, answers, setCurrentUser, navigate],
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
            {phoneEnabled && (
              <input
                type="tel"
                placeholder={phoneRequired ? "Phone *" : "Phone (optional)"}
                required={phoneRequired}
                maxLength={20}
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                className="h-11 px-4 rounded-xl text-sm bg-background ring-1 ring-border focus:outline-none focus:ring-primary/50 transition-shadow"
              />
            )}
            {nationalityEnabled && (
              <div>
                <label className="block text-[11px] text-muted-foreground mb-1 pl-0.5">
                  Nationality {nationalityRequired ? "*" : "(optional)"}
                </label>
                <CountrySelect
                  value={nationality}
                  onChange={setNationality}
                  valueType="name"
                  placeholder="Select nationality..."
                  className="w-full h-11 px-4 rounded-xl text-sm bg-background ring-1 ring-border focus:outline-none focus:ring-primary/50 transition-shadow"
                />
              </div>
            )}
            {dobEnabled && (
              <div>
                <label className="block text-[11px] text-muted-foreground mb-1 pl-0.5">
                  Date of birth {dobRequired ? "*" : "(optional)"}
                </label>
                <input
                  type="date"
                  required={dobRequired}
                  value={dob}
                  onChange={(e) => setDob(e.target.value)}
                  className="w-full h-11 px-4 rounded-xl text-sm bg-background ring-1 ring-border focus:outline-none focus:ring-primary/50 transition-shadow"
                />
              </div>
            )}
            {(countryEnabled || cityEnabled) && (
              <div className="grid grid-cols-2 gap-2">
                {countryEnabled && (
                  <div>
                    <label className="block text-[11px] text-muted-foreground mb-1 pl-0.5">
                      Country {countryRequired ? "*" : "(optional)"}
                    </label>
                    <CountrySelect
                      value={country}
                      onChange={setCountry}
                      valueType="code"
                      className="w-full h-11 px-4 rounded-xl text-sm bg-background ring-1 ring-border focus:outline-none focus:ring-primary/50 transition-shadow"
                    />
                  </div>
                )}
                {cityEnabled && (countryCities.length > 0 || country) ? (
                  <div>
                    <label className="block text-[11px] text-muted-foreground mb-1 pl-0.5">
                      City <span className="normal-case font-normal">{cityRequired ? "*" : "(optional)"}</span>
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
            )}
            {inviteEnabled && (
              <div className="flex flex-col gap-1">
                {urlInvite && inviteCode === urlInvite && (
                  <div className="flex items-center gap-1.5 text-xs font-medium text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-2.5 py-1 rounded-lg w-fit mb-0.5">
                    <Ticket className="size-3.5" />
                    Invite code {urlInvite} applied
                  </div>
                )}
                <input
                  type="text"
                  placeholder={inviteRequired ? "Invite code *" : "Invite code"}
                  required={inviteRequired}
                  value={inviteCode}
                  onChange={(e) => setInviteCode(e.target.value.toUpperCase())}
                  className="h-11 px-4 rounded-xl text-sm bg-background ring-1 ring-border focus:outline-none focus:ring-primary/50 transition-shadow font-mono"
                />
                <span className="text-xs text-muted-foreground px-1">
                  Enter your class invite code if given one.
                </span>
              </div>
            )}
            <PasswordInput
              placeholder="Password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="h-11 px-4 rounded-xl text-sm bg-background ring-1 ring-border focus:outline-none focus:ring-primary/50 transition-shadow"
            />

            {parentEnabled && (
              <>
                <button
                  type="button" onClick={() => setParentOpen((v) => !v)}
                  className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors w-fit cursor-pointer"
                >
                  <ChevronDown className={`size-3.5 transition-transform ${parentOpen || parentRequired ? "rotate-180" : ""}`} />
                  Parent/guardian information {parentRequired ? "*" : "(optional)"}
                </button>
                {(parentOpen || parentRequired) && (
                  <div className="flex flex-col gap-2 pl-3 border-l-2 border-border ml-1">
                    <input
                      type="text" placeholder="Parent/guardian name" required={parentRequired}
                      value={parentName} onChange={(e) => setParentName(e.target.value)}
                      className="h-10 px-3.5 rounded-xl text-sm bg-background ring-1 ring-border focus:outline-none focus:ring-primary/50 transition-shadow"
                    />
                    <input
                      type="tel" placeholder="Parent/guardian phone" required={parentRequired}
                      maxLength={20}
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
              </>
            )}

            {questions.length > 0 && (
              <div className="pt-2 border-t border-border/60">
                <CustomQuestionsFields
                  questions={questions}
                  answers={answers}
                  onChange={setAnswers}
                />
              </div>
            )}

            <Button size="xl" type="submit" disabled={loading} className="w-full mt-1">
              {loading ? "Signing up..." : "Sign up"}
            </Button>
          </form>
        </Card>

        <p className="mt-5 text-center text-sm text-muted-foreground">
          Already have an account?{" "}
          <Link
            to="/learn/login"
            search={inviteCode.trim() ? { invite: inviteCode.trim().toUpperCase() } : undefined}
            className="text-primary font-medium"
          >
            Log in
          </Link>
        </p>
      </div>
      <FinWidget />
    </div>
  );
}
