import type { Role } from "@/types/shared";
import logoPlain from "@/assets/logos/logo.png";
import logoAmbassador from "@/assets/logos/ambassador.svg";
import logoIntern from "@/assets/logos/intern.svg";

/** The plain SpacePoint wordmark — used on login and anywhere role-neutral. */
export const PLAIN_LOGO = logoPlain;

// Per-role logos. Only ambassador + intern have dedicated art so far; every
// other role falls back to the plain logo until you drop more in here.
const ROLE_LOGOS: Partial<Record<Role, string>> = {
  ambassador: logoAmbassador,
  intern: logoIntern,
  // teacher:   logoTeacher,      // share ambassadors domain — add when available
  // leader:    logoLeader,       // share interns domain — add when available
  // instructor / facilitator / applicant / admin → plain logo for now
};

/** Logo for a given role, falling back to the plain SpacePoint logo. */
export function roleLogo(role: Role | null | undefined): string {
  const logo = role ? ROLE_LOGOS[role] : undefined;
  return logo ?? PLAIN_LOGO;
}
