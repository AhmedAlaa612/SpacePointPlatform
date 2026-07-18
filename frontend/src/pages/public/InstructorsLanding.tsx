import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { PLAIN_LOGO } from "@/lib/logos";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { SiteFooter } from "@/components/layout/SiteFooter";
import { GLASS, BODY_BACKGROUND } from "@/lib/theme";

/**
 * Verbatim port of the reference app's public marketing page
 * (var/www/spacepoint_portal/backend/app/templates/landing.html).
 * Copy, layout, and styling are reproduced as-is — this is licensed
 * SpacePoint marketing content, not ours to reword or redesign.
 */

const HIGHLIGHTS = [
  {
    title: "Fully Funded Training",
    stat: "Worth 1,500 AED",
    body: "Selected applicants receive complete educational curriculum resources and certified hands-on SatKit instruction free of cost.",
    path: "M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
  },
  {
    title: "Paid Workshop Delivery",
    stat: "AED 300+ / Workshop",
    body: "Approved network instructors are hired on a part-time freelance basis and receive structured payouts per workshop delivery.",
    path: "M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z",
  },
  {
    title: "Flexible Schedule",
    stat: "4/10 Workshops Min.",
    body: "Designed to align with your university courses or job commitments. Simply select which sessions fit your availability.",
    path: "M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z",
  },
];

const ROADMAP = [
  { phase: "Phase 01", title: "Video Modules", body: "Watch expert-led educational content and submit your summaries directly inside the portal." },
  { phase: "Phase 02", title: "Research Challenge", body: "Complete a practical, structured research assignment targeting satellite and cubesat components." },
  { phase: "Phase 03", title: "On-Site Presentation", body: "Deliver a short presentation demonstrating your comprehension, research, and communication skills." },
  { phase: "Phase 04", title: "Certified Instructor", body: "Receive final evaluations, join our approved network, and begin delivering workshops." },
];

const FAQS = [
  {
    q: "What is the difference between the Intern and Instructor tracks?",
    a: (
      <>
        <p className="mb-2">
          <strong>
            <Link to="/interns" className="hover:underline">Intern track</Link>:
          </strong>{" "}
          Interns join SpacePoint for practical hands-on experience, supporting operations and technical development
          under the direct supervision of CEO Eng. Abdullah AlSalmani. Internships are structured educational
          opportunities and are unpaid.
        </p>
        <p>
          <strong>Instructor track:</strong> Approved instructors qualify as certified facilitators delivering
          workshops, events, and education programs, and are compensated on a part-time freelance basis.
        </p>
      </>
    ),
  },
  {
    q: "Are instructors paid? How much?",
    a: "Yes. Approved instructors operate on a freelance/part-time basis and are compensated when delivering workshops and events. Payouts vary based on program details, duration, and scope, typically starting from approximately AED 350+ per workshop or assignment.",
  },
  {
    q: "Do I need prior experience in satellites or space technology?",
    a: "No. SpacePoint welcomes candidates from diverse backgrounds. The portal learning modules and onboarding process are fully structured to provide you with all necessary satellite engineering and SatKit delivery training. A proactive mindset, commitment, and good communication skills are most valued.",
  },
  {
    q: "What is the onboarding process and does completing it guarantee acceptance?",
    a: "The onboarding roadmap comprises self-paced video lessons, a research assignment, and a mock presentation evaluated by our operations team. Completing these modules is mandatory to qualify but does not guarantee automatic acceptance. Final admission is determined by the quality of submissions, program slots, and interview outcomes (specifically for interns).",
  },
  {
    q: "Which co-working spaces and locations does SpacePoint operate from?",
    a: (
      <>
        Our active collaboration spaces include:
        <ul className="list-disc list-inside mt-2 space-y-1">
          <li><strong>Abu Dhabi:</strong> Athar+</li>
          <li><strong>Al Ain:</strong> MZN</li>
          <li><strong>Dubai:</strong> Expo City Dubai / MBRIF Offices (One Central)</li>
          <li><strong>Sharjah:</strong> Sheraa / SRTIP</li>
        </ul>
      </>
    ),
  },
  {
    q: "What are the core collaboration hours?",
    a: "Our core team collaboration and mentorship hours are 10:00 AM – 2:00 PM daily. Interns are generally expected to be available between 10:00 AM and 4:00 PM, subject to university courses, project schedules, and supervisor approval.",
  },
];

export function InstructorsLanding() {
  const [openFaq, setOpenFaq] = useState<number | null>(null);

  return (
    <div className="min-h-screen text-white" style={BODY_BACKGROUND}>
      <header className={`flex items-center justify-between gap-2 px-4 sm:px-6 py-3 sm:py-4 border-b border-white/10 ${GLASS}`}>
        <img src={PLAIN_LOGO} alt="SpacePoint" className="h-7 sm:h-10 w-auto object-contain shrink-0" />
        <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
          <ThemeToggle className="rounded-xl p-1.5 sm:p-2.5 text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground" />
          <Link
            to="/login"
            className="px-3 sm:px-5 py-1.5 sm:py-2 rounded-full font-medium tracking-wide text-white border border-white/10 hover:border-white/20 bg-white/5 hover:bg-white/10 transition-colors text-sm sm:text-base whitespace-nowrap"
          >
            Log In
          </Link>
          <Link
            to="/apply/instructor"
            className="px-3 sm:px-5 py-1.5 sm:py-2 rounded-full font-medium tracking-wide text-space-900 bg-space-accent hover:bg-space-hover transition-colors shadow-[0_0_15px_rgba(167,125,255,0.4)] text-sm sm:text-base whitespace-nowrap"
          >
            Apply Now
          </Link>
        </div>
      </header>

      <div className="relative overflow-hidden w-full flex-grow flex flex-col items-center py-12 md:py-20">
        {/* Ambient glowing backgrounds */}
        <div className="absolute top-20 left-10 w-72 h-72 sm:w-96 sm:h-96 bg-space-accent/15 rounded-full blur-[100px] -z-10 mix-blend-screen animate-pulse" />
        <div className="absolute bottom-40 right-10 w-72 h-72 sm:w-96 sm:h-96 bg-purple-600/15 rounded-full blur-[100px] -z-10 mix-blend-screen" />

        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 w-full flex flex-col items-center space-y-16 sm:space-y-24">
          {/* HERO SECTION */}
          <section className="w-full text-center max-w-4xl space-y-6 sm:space-y-8">
            <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-space-accent/30 bg-space-accent/5 text-space-accent text-xs sm:text-sm font-semibold tracking-wide">
              <span className="w-2 h-2 rounded-full bg-space-accent animate-ping" />
              Fully Funded Space Program Tracks 2026
            </div>

            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-display font-black text-white leading-tight tracking-tight">
              Shape the Future of <br className="hidden sm:inline" />
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-space-accent via-[#c0a0ff] to-[#653F84]">
                Space Tech Education
              </span>
            </h1>

            <p className="text-gray-300 text-base sm:text-lg max-w-2xl mx-auto leading-relaxed">
              Welcome to SpacePoint's Fully Funded Instructor &amp; Internship Track! Join our mission to deliver
              hands-on space and satellite development training to the next generation of innovators in the UAE.
            </p>

            <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-4">
              <Link
                to="/apply/instructor"
                className="w-full sm:w-auto inline-flex items-center justify-center px-8 py-4 rounded-xl font-bold tracking-wide text-space-900 bg-space-accent hover:bg-space-hover transition-all transform hover:-translate-y-0.5 shadow-[0_0_20px_rgba(167,125,255,0.4)]"
              >
                Start Application
                <svg className="w-5 h-5 ml-2 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                </svg>
              </Link>
              <Link
                to="/login"
                className="w-full sm:w-auto inline-flex items-center justify-center px-8 py-4 rounded-xl font-bold tracking-wide text-white border border-white/10 hover:border-white/20 bg-white/5 hover:bg-white/10 transition-all"
              >
                Sign In to Portal
              </Link>
            </div>
          </section>

          {/* HIGHLIGHTS / OPPORTUNITIES GRID */}
          <section className="w-full">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 lg:gap-8">
              {HIGHLIGHTS.map(({ title, stat, body, path }) => (
                <div
                  key={title}
                  className={`${GLASS} p-8 rounded-2xl relative overflow-hidden group hover:border-space-accent/30 transition-all duration-300 flex flex-col justify-between`}
                >
                  <div className="absolute -right-10 -top-10 w-28 h-28 bg-space-accent/10 rounded-full blur-2xl group-hover:bg-space-accent/20 transition-colors" />
                  <div className="space-y-4">
                    <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-space-accent to-[#653F84] flex items-center justify-center shadow-lg text-space-900">
                      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={path} />
                      </svg>
                    </div>
                    <h3 className="text-white font-display font-bold text-xl mt-4">{title}</h3>
                    <div className="text-2xl font-black text-space-accent">{stat}</div>
                    <p className="text-sm text-gray-400 leading-relaxed">{body}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* ONBOARDING TIMELINE / PIPELINE */}
          <section className="w-full max-w-4xl space-y-12">
            <div className="text-center space-y-3">
              <h2 className="font-display text-3xl font-bold text-white tracking-tight">Your Onboarding Roadmap</h2>
              <p className="text-gray-400 text-sm">Become a certified SpacePoint Instructor through 4 clear milestones</p>
            </div>

            <div className="relative grid grid-cols-1 md:grid-cols-4 gap-6 md:gap-8 pt-4">
              {ROADMAP.map(({ phase, title, body }, i) => (
                <div
                  key={phase}
                  className={`${GLASS} p-6 rounded-2xl relative space-y-3 border-t-2 ${i === 3 ? "border-t-[#653F84]" : "border-t-space-accent"}`}
                >
                  <div className="text-xs font-bold text-space-accent uppercase tracking-widest">{phase}</div>
                  <h4 className="text-white font-semibold text-base">{title}</h4>
                  <p className="text-xs text-gray-400 leading-relaxed">{body}</p>
                </div>
              ))}
            </div>
          </section>

          {/* INTERACTIVE FAQ SECTION */}
          <section className="w-full max-w-4xl space-y-12">
            <div className="text-center space-y-3">
              <h2 className="font-display text-3xl font-bold text-white tracking-tight">Frequently Asked Questions</h2>
              <p className="text-gray-400 text-sm">Find quick answers to common questions about the program tracks</p>
            </div>

            <div className="space-y-4">
              {FAQS.map(({ q, a }, i) => {
                const open = openFaq === i;
                return (
                  <div key={q} className={`${GLASS} rounded-2xl overflow-hidden transition-all duration-300 ${open ? "border-space-accent/40" : ""}`}>
                    <button
                      onClick={() => setOpenFaq(open ? null : i)}
                      className="w-full flex items-center justify-between px-6 py-5 text-left text-white font-display font-semibold hover:bg-white/[0.02] transition-colors focus:outline-none"
                    >
                      <span>{q}</span>
                      <svg
                        className={`w-5 h-5 text-space-accent transform transition-transform duration-300 shrink-0 ml-4 ${open ? "rotate-180" : ""}`}
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                      </svg>
                    </button>
                    {open && (
                      <div className="px-6 pb-6 text-sm text-gray-300 leading-relaxed border-t border-white/5 pt-4">
                        {a}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </section>

          {/* WORKSHOPS GALLERY */}
          <section className="w-full space-y-8 relative">
            <div className="text-center space-y-3">
              <h2 className="font-display text-3xl font-bold text-white tracking-tight">Join The Missions</h2>
              <p className="text-gray-400 text-sm">Step into active satellite training and workshop experiences across the UAE</p>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-3 gap-4 lg:gap-6 w-full">
              {Array.from({ length: 6 }).map((_, i) => (
                <div
                  key={i}
                  className={`aspect-[4/3] rounded-2xl overflow-hidden ${GLASS} group relative shadow-lg transform hover:-translate-y-1 hover:shadow-space-accent/20 hover:shadow-2xl transition-all duration-300`}
                >
                  <img
                    src={`/static/instructors/placeholder_${i}.jpg`}
                    onError={(e) => { e.currentTarget.style.display = "none"; }}
                    alt="Instructor At Workshop"
                    className="absolute inset-0 w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                  />
                </div>
              ))}
            </div>

            <div className="absolute -bottom-6 -right-2 rounded-2xl p-4 shadow-2xl border border-space-accent/30 z-10 bg-space-900 flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-space-accent/10 flex items-center justify-center text-space-accent">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"
                  />
                </svg>
              </div>
              <div>
                <div className="text-xl font-display font-extrabold text-white">10+ Schools</div>
                <div className="text-[10px] text-space-accent uppercase font-bold tracking-wider">Across the UAE</div>
              </div>
            </div>
          </section>
        </div>
      </div>

      <SiteFooter />
    </div>
  );
}

export default InstructorsLanding;
