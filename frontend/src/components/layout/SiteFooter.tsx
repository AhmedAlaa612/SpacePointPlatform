import { PLAIN_LOGO } from "@/lib/logos";
import { GLASS } from "@/lib/theme";

/**
 * Verbatim port of base.html's global footer (Contact Us / Follow Our Mission /
 * copyright) — shared across the public landing page, the apply flow, and the
 * authenticated applicant shell, matching the reference app's base.html which
 * renders this on every page.
 */
export function SiteFooter() {
  return (
    <footer className={`border-t border-white/10 ${GLASS}`}>
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-12 grid grid-cols-1 md:grid-cols-3 gap-10">
        <div className="space-y-3">
          <img src={PLAIN_LOGO} alt="SpacePoint" className="h-9 w-auto object-contain" />
          <p className="text-sm text-gray-400 leading-relaxed max-w-xs">
            Empowering the next generation of space explorers, innovators, and engineers through hands-on satellite
            education and mission experiences.
          </p>
        </div>

        <div className="space-y-3">
          <h4 className="text-white font-display font-bold tracking-wide text-sm">Contact Us</h4>
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
            info@spacepoint.ae
          </div>
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
            </svg>
            +971 56 298 7005
          </div>
        </div>

        <div className="space-y-3">
          <h4 className="text-white font-display font-bold tracking-wide text-sm">Follow Our Mission</h4>
          <div className="flex items-center gap-3 text-gray-400">
            <a
              href="https://www.instagram.com/spacepoint.ae"
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Instagram"
              className="w-9 h-9 rounded-full border border-white/10 flex items-center justify-center hover:text-space-accent hover:border-space-accent/40 transition-colors"
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0 5.838a4 4 0 100 8 4 4 0 000-8zm5.406-.65a1 1 0 100-2 1 1 0 000 2z" />
              </svg>
            </a>
            <a
              href="https://www.linkedin.com/company/spacepointae"
              target="_blank"
              rel="noopener noreferrer"
              aria-label="LinkedIn"
              className="w-9 h-9 rounded-full border border-white/10 flex items-center justify-center hover:text-space-accent hover:border-space-accent/40 transition-colors"
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <path d="M19 3a2 2 0 012 2v14a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h14zM8.339 18.338V9.865H5.667v8.473h2.672zM7.005 8.727c.9 0 1.464-.598 1.464-1.348-.017-.766-.564-1.349-1.446-1.349-.881 0-1.463.583-1.463 1.35 0 .749.564 1.347 1.428 1.347h.017zm11.334 9.611V13.61c0-2.42-1.293-3.546-3.017-3.546-1.391 0-2.014.766-2.362 1.303V9.865h-2.67v8.473h2.67v-4.732c0-.253.018-.505.093-.686.204-.505.668-1.028 1.447-1.028 1.02 0 1.428.777 1.428 1.916v4.53h2.412z" />
              </svg>
            </a>
            <a
              href="https://www.tiktok.com/@spacepoint.ae"
              target="_blank"
              rel="noopener noreferrer"
              aria-label="TikTok"
              className="w-9 h-9 rounded-full border border-white/10 flex items-center justify-center hover:text-space-accent hover:border-space-accent/40 transition-colors"
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z" />
              </svg>
            </a>
          </div>
        </div>
      </div>
      <div className="border-t border-white/5 px-4 sm:px-6 lg:px-8 py-5 max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-gray-500">
        <span>© copyright SpacePoint 2026. All rights reserved.</span>
        <span>Built for Explorers ♥</span>
      </div>
    </footer>
  );
}
