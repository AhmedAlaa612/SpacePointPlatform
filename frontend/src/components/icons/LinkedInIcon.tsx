import type { SVGProps } from "react"

export function LinkedInIcon({ className = "w-4 h-4", ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
      {...props}
    >
      <rect width="24" height="24" rx="4.5" fill="#0A66C2" />
      <path d="M7.12 9.5H4.5V18H7.12V9.5Z" fill="#FFFFFF" />
      <path
        d="M5.81 5.5C4.94 5.5 4.3 6.13 4.3 6.94C4.3 7.74 4.93 8.38 5.79 8.38C6.68 8.38 7.3 7.74 7.31 6.94C7.3 6.13 6.67 5.5 5.81 5.5Z"
        fill="#FFFFFF"
      />
      <path
        d="M13.25 9.5H10.65V18H13.25V13.63C13.25 12.44 13.79 11.66 14.88 11.66C15.93 11.66 16.32 12.46 16.32 13.63V18H18.92V13.28C18.92 10.84 17.65 9.38 15.65 9.38C14.54 9.38 13.74 9.92 13.25 10.63V9.5Z"
        fill="#FFFFFF"
      />
    </svg>
  )
}
