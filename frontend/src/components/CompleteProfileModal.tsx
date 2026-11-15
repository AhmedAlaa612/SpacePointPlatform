import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { isAxiosError } from "axios";
import { LogOut } from "lucide-react";
import { updateMeApi } from "@/api/auth";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { CountrySelect } from "@/components/ui/CountrySelect";
import { CitySelect } from "@/components/ui/CitySelect";
import { LanguageMultiSelect } from "@/components/ui/LanguageMultiSelect";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export function CompleteProfileModal() {
  const { user } = useAuth();
  const missing = user?.missing_profile_fields ?? [];

  if (!user || missing.length === 0) return null;

  return (
    <Dialog open={true} onOpenChange={() => {}}>
      <CompleteProfileForm key={missing.join(",")} missing={missing} />
    </Dialog>
  );
}

function CompleteProfileForm({ missing }: { missing: string[] }) {
  const { user, setCurrentUser, logout } = useAuth();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const [phone, setPhone] = useState(user?.phone ?? "");
  const [nationality, setNationality] = useState(user?.nationality ?? "");
  const [birthdate, setBirthdate] = useState(
    (user?.birthdate ?? user?.date_of_birth ?? "").split("T")[0],
  );
  const [country, setCountry] = useState(user?.country ?? "");
  const [cityId, setCityId] = useState(user?.city_id ?? "");
  const [cityOther, setCityOther] = useState(user?.city_other ?? "");
  const [universityName, setUniversityName] = useState(user?.organization_name ?? "");
  const [studentId, setStudentId] = useState(user?.student_id ?? "");
  const [workStatus, setWorkStatus] = useState(user?.work_status ?? "");
  const [graduatedUniversity, setGraduatedUniversity] = useState(user?.graduated_university ?? "");
  const [fluentLanguages, setFluentLanguages] = useState<string[]>(user?.fluent_languages ?? []);
  const [error, setError] = useState<string | null>(null);

  const has = (key: string) => missing.includes(key);
  const needsCountryPicker = has("country") || (has("city") && !user?.country);
  const effectiveCountry = needsCountryPicker ? country : (user?.country ?? "");
  const isInstructor =
    user?.roles?.includes("instructor") || user?.roles?.includes("facilitator");

  const validate = (): string | null => {
    if (has("phone") && !phone.trim()) return "Please enter your phone number.";
    if (has("nationality") && !nationality.trim()) return "Please select your nationality.";
    if (has("birthdate") && !birthdate) return "Please enter your date of birth.";
    if (needsCountryPicker && !country) return "Please select your current country.";
    if (has("city") && effectiveCountry && !cityId && !cityOther.trim()) {
      return "Please select or enter your city.";
    }
    if (has("university_name") && !universityName.trim()) {
      return "Please enter your university or institution.";
    }
    if (has("student_id") && !studentId.trim()) {
      return "Please enter your student / university ID.";
    }
    if (has("work_status") && !workStatus.trim()) return "Please enter your work status.";
    if (has("graduated_university") && !graduatedUniversity.trim()) {
      return "Please enter your graduated university.";
    }
    if (has("fluent_languages") && fluentLanguages.length === 0) {
      return "Please select at least one fluent language.";
    }
    return null;
  };

  const save = useMutation({
    mutationFn: async () => {
      const payload: Parameters<typeof updateMeApi>[0] = {};
      if (has("phone")) payload.phone = phone.trim();
      if (has("nationality")) payload.nationality = nationality.trim();
      if (has("birthdate")) {
        payload.birthdate = birthdate;
        payload.date_of_birth = birthdate;
      }
      if (needsCountryPicker) payload.country = country;
      if (has("city")) {
        if (isInstructor && cityId) {
          payload.city_of_residence_id = cityId;
        }
        if (cityId) payload.city_id = cityId;
        if (cityOther.trim()) payload.city_other = cityOther.trim();
      }
      if (has("university_name")) payload.university_name = universityName.trim();
      if (has("student_id")) payload.student_id = studentId.trim();
      if (has("work_status")) payload.work_status = workStatus.trim();
      if (has("graduated_university")) payload.graduated_university = graduatedUniversity.trim();
      if (has("fluent_languages")) payload.fluent_languages = fluentLanguages;
      return updateMeApi(payload);
    },
    onSuccess: (updated) => {
      setError(null);
      setCurrentUser(updated);
      void queryClient.invalidateQueries({ queryKey: ["me"] });
    },
    onError: (err: unknown) => {
      if (isAxiosError(err) && typeof err.response?.data?.detail === "string") {
        setError(err.response.data.detail);
      } else {
        setError("Failed to save your details. Please try again.");
      }
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const msg = validate();
    if (msg) {
      setError(msg);
      return;
    }
    setError(null);
    save.mutate();
  };

  const handleSignOut = async () => {
    const isLearn = window.location.pathname.startsWith("/learn");
    await logout();
    void navigate({ to: isLearn ? "/learn/login" : "/login" });
  };

  const inputCls =
    "w-full h-11 rounded-xl border border-border bg-background px-3.5 text-sm text-foreground focus:outline-none focus:border-primary transition-colors";
  const labelCls = "block text-xs font-medium text-muted-foreground mb-1.5";

  return (
    <DialogContent
      showCloseButton={false}
      onInteractOutside={(e) => e.preventDefault()}
      onEscapeKeyDown={(e) => e.preventDefault()}
      className="sm:max-w-md max-h-[90vh] overflow-y-auto"
    >
      <DialogHeader>
        <DialogTitle className="font-display text-base">Complete your profile</DialogTitle>
        <DialogDescription className="text-xs mt-0.5">
          Please fill in the required details below to continue using your account.
        </DialogDescription>
      </DialogHeader>

      <form onSubmit={handleSubmit} className="flex flex-col gap-3.5 py-2">
        {has("nationality") && (
          <div>
            <label className={labelCls}>Nationality *</label>
            <CountrySelect
              value={nationality}
              onChange={setNationality}
              valueType="name"
              placeholder="Select nationality..."
              className={inputCls}
            />
          </div>
        )}

        {has("birthdate") && (
          <div>
            <label className={labelCls}>Date of birth *</label>
            <input
              type="date"
              value={birthdate}
              onChange={(e) => setBirthdate(e.target.value)}
              className={inputCls}
              required
            />
          </div>
        )}

        {needsCountryPicker && (
          <div>
            <label className={labelCls}>Current country *</label>
            <CountrySelect
              value={country}
              onChange={(val) => {
                setCountry(val);
                setCityId("");
                setCityOther("");
              }}
              valueType="code"
              placeholder="Select country..."
              className={inputCls}
            />
          </div>
        )}

        {has("city") && effectiveCountry && (
          <div>
            <label className={labelCls}>City *</label>
            <CitySelect
              country={effectiveCountry}
              value={cityId}
              onChange={(val) => {
                setCityId(val);
                if (val) setCityOther("");
              }}
              otherValue={cityOther}
              onOtherChange={setCityOther}
              className={inputCls}
            />
          </div>
        )}

        {has("phone") && (
          <div>
            <label className={labelCls}>Phone / WhatsApp *</label>
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+971 50 000 0000"
              className={inputCls}
              required
            />
          </div>
        )}

        {has("university_name") && (
          <div>
            <label className={labelCls}>University / Institution *</label>
            <input
              value={universityName}
              onChange={(e) => setUniversityName(e.target.value)}
              placeholder="e.g. United Arab Emirates University"
              className={inputCls}
              required
            />
          </div>
        )}

        {has("student_id") && (
          <div>
            <label className={labelCls}>University / Student ID *</label>
            <input
              value={studentId}
              onChange={(e) => setStudentId(e.target.value)}
              placeholder="e.g. H00412345"
              className={inputCls}
              required
            />
          </div>
        )}

        {has("work_status") && (
          <div>
            <label className={labelCls}>Work status *</label>
            <input
              value={workStatus}
              onChange={(e) => setWorkStatus(e.target.value)}
              placeholder="e.g. Engineer, University Student"
              className={inputCls}
              required
            />
          </div>
        )}

        {has("graduated_university") && (
          <div>
            <label className={labelCls}>Graduated university *</label>
            <input
              value={graduatedUniversity}
              onChange={(e) => setGraduatedUniversity(e.target.value)}
              placeholder="e.g. Khalifa University"
              className={inputCls}
              required
            />
          </div>
        )}

        {has("fluent_languages") && (
          <div>
            <label className={labelCls}>Fluent languages *</label>
            <LanguageMultiSelect
              value={fluentLanguages}
              onChange={setFluentLanguages}
              placeholder="Select fluent languages..."
            />
          </div>
        )}

        {error && <p className="text-xs text-destructive">{error}</p>}

        <DialogFooter className="pt-2 flex-row items-center justify-between sm:justify-between">
          <button
            type="button"
            onClick={() => void handleSignOut()}
            className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
          >
            <LogOut className="size-3.5" /> Sign out
          </button>
          <Button type="submit" disabled={save.isPending}>
            {save.isPending ? "Saving..." : "Save & Continue"}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}
