import { useLocation } from "@tanstack/react-router";
import ambassadorIcon from "@/assets/icons/ambassador-icon.png";

const DOMAIN_LABELS: Record<string, string> = {
  interns: "Interns",
  ambassadors: "Ambassadors",
  instructors: "Instructors",
  admin: "Admin",
};

export function DomainIcon({ className }: { className?: string }) {
  const { pathname } = useLocation();
  const domain = pathname.split("/")[1];
  const label = DOMAIN_LABELS[domain] ?? "SpacePoint";

  return (
    <svg
      viewBox="0 0 527 123"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={`text-[#1E1E1E] dark:text-white ${className ?? ""}`}
    >
        <image
          href={ambassadorIcon}
          width="324"
          height="75"
          preserveAspectRatio="none"
        />
        <text
          transform="translate(324 51)"
          fill="currentColor"
          fontFamily="Just Another Hand"
          fontSize="70"
          letterSpacing="0"
          xmlSpace="preserve"
          style={{ whiteSpace: "pre" }}
        >
          <tspan x="0" y="49.2188">{label}</tspan>
        </text>
    </svg>
  );
}
