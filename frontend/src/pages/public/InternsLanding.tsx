import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { PLAIN_LOGO } from "@/lib/logos";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { SiteFooter } from "@/components/layout/SiteFooter";
import { GLASS, BODY_BACKGROUND } from "@/lib/theme";

/**
 * Verbatim port of the marketing copy in "Internship Page.md" — this is
 * licensed SpacePoint marketing content, not ours to reword or redesign.
 * Layout/classes are cloned from InstructorsLanding.tsx.
 */

const HIGHLIGHTS = [
  {
    title: "Real Engineering Problems",
    stat: "R&D Projects",
    body: "Rather than assigning routine tasks, we challenge interns to solve real engineering problems and contribute to ongoing R&D projects — satellites, AI, drones, robotics, embedded systems, and advanced manufacturing.",
    path: "M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z",
  },
  {
    title: "Structured Mentorship",
    stat: "1-on-1 Reviews",
    body: "Continuous guidance, technical reviews, and mentorship from experienced engineers. The more effort an intern invests, the more rewarding the experience becomes.",
    path: "M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-1.13a4 4 0 10-4-4 4 4 0 004 4zm6-4a4 4 0 11-8 0 4 4 0 018 0z",
  },
  {
    title: "Internship Duration",
    stat: "3 Months",
    body: "Standard duration is 3 months; a 2-month internship may be arranged depending on university requirements. High performers may be offered an extension.",
    path: "M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z",
  },
];

const DISCIPLINES = [
  "Electrical Engineering",
  "Mechanical Engineering",
  "Aerospace Engineering",
  "Computer Engineering",
  "Software Engineering",
  "Communications Engineering",
  "Artificial Intelligence",
  "Robotics and Mechatronics",
  "Other closely related engineering disciplines",
];

const DOMAINS = [
  "Satellite subsystem development",
  "Drone technologies",
  "Artificial Intelligence",
  "Computer Vision",
  "Embedded Systems",
  "PCB Design",
  "Mechanical Design",
  "Remote Sensing",
  "Robotics",
  "Space Software",
  "Digital Twins",
  "IoT Systems",
  "Educational Technology Platforms",
];

const LEARN_TRACKS = [
  {
    title: "Electrical & Electronics Engineering",
    items: [
      "Electronic circuit design",
      "Circuit simulation",
      "PCB design and routing",
      "Embedded electronics",
      "Power systems",
      "Sensor integration",
      "System architecture",
      "Hardware testing and validation",
    ],
  },
  {
    title: "Mechanical & Aerospace Engineering",
    items: [
      "CAD modelling",
      "Structural analysis",
      "Thermal analysis",
      "Design optimization",
      "Mechanical assemblies",
      "Product prototyping",
      "Manufacturing considerations",
      "Satellite structural design",
    ],
  },
  {
    title: "Software, AI & Computer Engineering",
    items: [
      "Computer Vision",
      "Artificial Intelligence",
      "Embedded Software",
      "ESP32 & STM32 Development",
      "Edge AI optimization",
      "Dashboard development",
      "Data visualization",
      "Image processing",
      "Flowchart design",
      "Software architecture",
      "API integration",
    ],
  },
];

const ENGINEERING_EMPHASIS = [
  {
    label: "System Architecture",
    path: "M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z",
  },
  {
    label: "Functional Block Diagrams",
    path: "M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z",
  },
  {
    label: "Engineering Documentation",
    path: "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z",
  },
  {
    label: "Design Reviews",
    path: "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4",
  },
  {
    label: "Technical Presentations",
    path: "M8 13v-1m4 1v-3m4 3V8M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z",
  },
  {
    label: "Project Planning",
    path: "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01",
  },
  {
    label: "Testing Methodologies",
    path: "M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z",
  },
];

const ROADMAP = [
  { phase: "Step 01", title: "Define project objectives" },
  { phase: "Step 02", title: "Break projects into milestones" },
  { phase: "Step 03", title: "Hold regular technical reviews" },
  { phase: "Step 04", title: "Receive engineering feedback" },
  { phase: "Step 05", title: "Present progress periodically" },
  { phase: "Step 06", title: "Produce final technical deliverables" },
];

type Project = { student: string; title: string; image: string; description: string };

const PROJECTS: Project[] = [
  {
    student: "Abdalla Osama",
    title: "Real-Time Satellite Telemetry Dashboard",
    image: "/static/interns/projects/abdalla-osama-dashboard-mqtt.jpg",
    description:
      "A complete telemetry pipeline for a satellite simulation: ESP32 sensor acquisition, wireless HC-12 transmission, an MQTT broker, and live visualization with InfluxDB and Grafana.",
  },
  {
    student: "Kassam Dakhlalah",
    title: "CubeSat Mission Control",
    image: "/static/interns/projects/kassam-dakhlalah-mission-control.jpg",
    description:
      "An interactive ground-station interface visualizing CubeSat health in real time — live charts, 3D orientation models, global tracking maps, and historical logs.",
  },
  {
    student: "Lamya AlDhaheri",
    title: "AI Space Debris Detection & Stabilization",
    image: "/static/interns/projects/lamya-aldhaheri-ai-debris-1.jpg",
    description:
      "An embedded system that detects space debris with an AI vision model and stabilizes orientation using an IMU and reaction wheel, built on RTOS-based task structuring.",
  },
  {
    student: "Nour Arnaout",
    title: "1U CubeSat Thermal Analysis",
    image: "/static/interns/projects/nour-arnaout-thermal.jpg",
    description:
      "Thermal simulation of SpacePoint's 1U CubeSat in ANSYS Fluent — hot case, cold case, and a transient full-orbit cycle with solar flux, albedo, and Earth IR.",
  },
  {
    student: "Rayan AlDhaheri",
    title: "CubeSat Electrical Power System",
    image: "/static/interns/projects/rayan-aldhaheri-eps.jpg",
    description:
      "A complete EPS design: solar array input, MPPT stage, battery storage, and regulated power distribution to the onboard computer and sensor subsystems.",
  },
];

type Alumnus = { name: string; field: string; role: string; linkedin: string; photo: string | null };

const ALUMNI: Alumnus[] = [
  { name: "Halima Barshed", field: "Communication Engineering", role: "Engineer, Ericsson", linkedin: "https://www.linkedin.com/in/halima-barshed-911741208", photo: "/static/interns/alumni/halima-barshed.png" },
  { name: "Sami Meetani", field: "Electrical Engineering", role: "Amazon Robotics, USA", linkedin: "https://www.linkedin.com/in/samimeetani", photo: "/static/interns/alumni/sami-meetani.png" },
  { name: "Muzoon Almazrouei", field: "Aerospace Engineering", role: "Intern, Dassault Aviation, France", linkedin: "https://www.linkedin.com/in/muzoon-almazrouei-62b184369", photo: "/static/interns/alumni/muzoon-almazrouei.png" },
  { name: "Kassam Dakhlalah", field: "Robotics and Embedded Systems", role: "Engineer, Lootah Tech", linkedin: "https://www.linkedin.com/in/eng-kassam-dakhlalah-2b44bb207", photo: "/static/interns/alumni/kassam-dakhlalah.png" },
  { name: "Mariam Alketbi", field: "Thermal Engineering", role: "Intern, MBRSC · Dassault Aviation", linkedin: "https://www.linkedin.com/in/maryam-al-ketbi-9a88b8290", photo: "/static/interns/alumni/mariam-alketbi.png" },
  { name: "Rayan AlDhaheri", field: "Electrical Engineering", role: "Intern, EDGE", linkedin: "https://www.linkedin.com/in/rayan-aldhaheri", photo: "/static/interns/alumni/rayan-aldhaheri.png" },
  { name: "Ziad Sefelnasr", field: "Master's Degree", role: "Germany", linkedin: "https://www.linkedin.com/in/ziad-sefelnasr-7ba3a220b", photo: "/static/interns/alumni/ziad-sefelnasr.png" },
  { name: "Noor Albastaki", field: "Health, Safety and Environment", role: "Intern, ADNOC Group | Rashid Hospital", linkedin: "https://www.linkedin.com/in/noor-albastaki", photo: "/static/interns/alumni/noor-albastaki.png" },
  { name: "Sawsan Omira", field: "Aerospace Engineering", role: "Intern, Emirates", linkedin: "https://www.linkedin.com/in/sawsanomira", photo: "/static/interns/alumni/sawsan-omira.png" },
  { name: "Lameya AlDhaheri", field: "Electrical Engineering", role: "Research Assistant, UAEU | ADNOC", linkedin: "https://www.linkedin.com/in/lameya-aldhaheri-194bb5289", photo: null },
  { name: "Hassa Alketbi", field: "Aerospace Engineering", role: "Satellite Engineer, NSSTC", linkedin: "https://www.linkedin.com/in/hassa-alketbi-0a08b430a", photo: null },
  { name: "Osama Akila", field: "Machine Learning", role: "Intern, Smart Link", linkedin: "https://www.linkedin.com/in/osama-mahmoud-akila-9a847a268", photo: null },
];

const DESTINATION_ORGS = [
  "Technology Innovation Institute (TII)",
  "EDGE Group",
  "NSSTC",
  "MBRSC",
  "Amazon Robotics",
  "Dassault Aviation (France)",
];

const WHAT_WE_LOOK_FOR = [
  "Enjoy solving challenging problems",
  "Take initiative",
  "Learn independently",
  "Ask thoughtful questions",
  "Document their work",
  "Collaborate effectively",
  "Strive for continuous improvement",
];

const FAQS = [
  {
    q: "How long is the internship?",
    a: (
      <>
        <p className="mb-2">
          The standard duration is <strong>3 months</strong>. In some cases, a 2-month internship may be arranged
          depending on university requirements.
        </p>
        <p className="mb-2">High performers may be offered an extension based on:</p>
        <ul className="list-disc list-inside space-y-1">
          <li>Project progress</li>
          <li>Performance</li>
          <li>Team requirements</li>
          <li>Mutual interest</li>
        </ul>
      </>
    ),
  },
  {
    q: "Is the internship paid?",
    a: "Internships are structured educational opportunities and are unpaid. Students are expected to take ownership of their learning while receiving continuous guidance, technical reviews, and mentorship from experienced engineers.",
  },
  {
    q: "What are the working hours and locations?",
    a: (
      <>
        <p className="mb-2">
          Our core team collaboration and mentorship hours are 10:00 AM – 2:00 PM daily. Interns are generally
          expected to be available between 10:00 AM and 4:00 PM, subject to university courses, project schedules,
          and supervisor approval.
        </p>
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
    q: "Do I need prior experience?",
    a: "No prior experience is required. We value curiosity more than experience — a proactive mindset, commitment, and good communication skills matter far more than a polished resume.",
  },
  {
    q: "What's the difference between the Intern and Instructor tracks?",
    a: (
      <>
        <p className="mb-2">
          <strong>Intern track:</strong> Interns join SpacePoint for practical hands-on experience, supporting
          operations and technical development under the direct supervision of CEO Eng. Abdullah AlSalmani.
          Internships are structured educational opportunities and are unpaid.
        </p>
        <p className="mb-2">
          <strong>Instructor track:</strong> Approved instructors qualify as certified facilitators delivering
          workshops, events, and education programs, and are compensated on a part-time freelance basis.
        </p>
        <Link to="/instructors" className="text-space-accent font-semibold hover:underline">
          Learn more about the Instructor track →
        </Link>
      </>
    ),
  },
];

const LEARN_PREVIEW_COUNT = 4;

export function InternsLanding() {
  const [openFaq, setOpenFaq] = useState<number | null>(null);
  const [openProject, setOpenProject] = useState<number | null>(null);
  const [expandedLearn, setExpandedLearn] = useState<Set<number>>(new Set());

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
            to="/apply/intern"
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
              SpacePoint Internship Program 2026
            </div>

            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-display font-black text-white leading-tight tracking-tight">
              Build the Future. <br className="hidden sm:inline" />
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-space-accent via-[#c0a0ff] to-[#653F84]">
                Engineer It.
              </span>
            </h1>

            <p className="text-gray-300 text-base sm:text-lg max-w-xl mx-auto leading-relaxed">
              Internships at SpacePoint are more than a work experience — they are a guided engineering journey that
              turns students into confident innovators and future industry leaders.
            </p>

            <div className="flex items-center justify-center gap-4">
              <span className="h-px w-10 sm:w-16 bg-gradient-to-r from-transparent to-space-accent/60" />
              <span className="font-display font-bold text-lg sm:text-xl text-space-accent whitespace-nowrap">
                We don't spoon-feed. We mentor.
              </span>
              <span className="h-px w-10 sm:w-16 bg-gradient-to-l from-transparent to-space-accent/60" />
            </div>

            <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-4">
              <Link
                to="/apply/intern"
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

          {/* HIGHLIGHTS GRID */}
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

          {/* WHO CAN APPLY */}
          <section className="w-full max-w-4xl space-y-8">
            <div className="text-center space-y-3">
              <h2 className="font-display text-3xl font-bold text-white tracking-tight">Who Can Apply?</h2>
              <p className="text-gray-400 text-sm">
                We welcome students and recent graduates from engineering disciplines across the board
              </p>
            </div>
            <div className="flex flex-wrap justify-center gap-3">
              {DISCIPLINES.map((d) => (
                <span key={d} className={`${GLASS} px-4 py-2 rounded-full text-sm text-gray-300`}>{d}</span>
              ))}
            </div>
          </section>

          {/* WHAT YOU'LL WORK ON */}
          <section className="w-full max-w-4xl space-y-8">
            <div className="text-center space-y-3">
              <h2 className="font-display text-3xl font-bold text-white tracking-tight">What You'll Work On</h2>
              <p className="text-gray-400 text-sm">
                Every intern follows a structured project roadmap while contributing to real products and research
                initiatives
              </p>
            </div>
            <div className="flex flex-wrap justify-center gap-3">
              {DOMAINS.map((d) => (
                <div
                  key={d}
                  className={`${GLASS} rounded-xl px-4 py-3 text-sm text-gray-300 text-center flex items-center justify-center w-[calc(50%-0.375rem)] sm:w-[calc(33.333%-0.5rem)] lg:w-[calc(25%-0.5625rem)]`}
                >
                  {d}
                </div>
              ))}
            </div>
            <p className="text-gray-400 text-sm text-center">
              Projects are carefully designed to simulate real engineering workflows used across industry.
            </p>
          </section>

          {/* WHAT YOU'LL LEARN */}
          <section className="w-full space-y-8">
            <div className="text-center space-y-3">
              <h2 className="font-display text-3xl font-bold text-white tracking-tight">What You'll Learn</h2>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 lg:gap-8">
              {LEARN_TRACKS.map(({ title, items }, i) => {
                const expanded = expandedLearn.has(i);
                const visible = expanded ? items : items.slice(0, LEARN_PREVIEW_COUNT);
                const hiddenCount = items.length - LEARN_PREVIEW_COUNT;
                return (
                  <div key={title} className={`${GLASS} p-8 rounded-2xl relative overflow-hidden`}>
                    <div className="space-y-4">
                      <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-space-accent to-[#653F84] flex items-center justify-center shadow-lg text-space-900">
                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                        </svg>
                      </div>
                      <h3 className="text-white font-display font-bold text-lg">{title}</h3>
                      <ul className="space-y-1.5 text-sm text-gray-400">
                        {visible.map((it) => (
                          <li key={it} className="flex items-start gap-2">
                            <span className="text-space-accent mt-1">•</span>
                            <span>{it}</span>
                          </li>
                        ))}
                      </ul>
                      {hiddenCount > 0 && (
                        <button
                          onClick={() =>
                            setExpandedLearn((prev) => {
                              const next = new Set(prev);
                              if (expanded) next.delete(i);
                              else next.add(i);
                              return next;
                            })
                          }
                          className="text-space-accent text-xs font-semibold hover:underline"
                        >
                          {expanded ? "Show less" : `+${hiddenCount} more`}
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          {/* ENGINEERING BEFORE CODING */}
          <section className="w-full max-w-4xl space-y-8">
            <div className="text-center space-y-3">
              <h2 className="font-display text-3xl font-bold text-white tracking-tight">Engineering Before Coding</h2>
              <p className="text-white font-semibold text-lg">Good engineers design before they build.</p>
            </div>
            <div className="flex flex-wrap justify-center gap-3 sm:gap-4">
              {ENGINEERING_EMPHASIS.map(({ label, path }) => (
                <div
                  key={label}
                  className={`${GLASS} rounded-xl px-4 py-3 flex items-center gap-3 hover:border-space-accent/30 transition-all`}
                >
                  <div className="w-8 h-8 rounded-lg bg-space-accent/10 flex items-center justify-center text-space-accent shrink-0">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={path} />
                    </svg>
                  </div>
                  <span className="text-sm text-gray-300 whitespace-nowrap">{label}</span>
                </div>
              ))}
            </div>
            <p className="text-gray-400 text-sm italic text-center">
              Understanding <em>why</em> a system works is just as important as making it work.
            </p>
          </section>

          {/* MENTORSHIP ROADMAP */}
          <section className="w-full max-w-4xl space-y-12">
            <div className="text-center space-y-3">
              <h2 className="font-display text-3xl font-bold text-white tracking-tight">A Structured Mentorship Experience</h2>
              <p className="text-gray-400 text-sm">Every internship follows a guided structure</p>
            </div>

            <div className="relative grid grid-cols-1 md:grid-cols-3 gap-6 md:gap-8 pt-4">
              {ROADMAP.map(({ phase, title }, i) => (
                <div
                  key={phase}
                  className={`${GLASS} p-6 rounded-2xl relative space-y-3 border-t-2 ${i === ROADMAP.length - 1 ? "border-t-[#653F84]" : "border-t-space-accent"}`}
                >
                  <div className="text-xs font-bold text-space-accent uppercase tracking-widest">{phase}</div>
                  <h4 className="text-white font-semibold text-base">{title}</h4>
                </div>
              ))}
            </div>
            <p className="text-gray-400 text-sm text-center">
              This ensures every intern graduates with both technical knowledge and professional engineering
              experience.
            </p>
          </section>

          {/* STUDENT PROJECTS GALLERY */}
          <section className="w-full space-y-8">
            <div className="text-center space-y-3">
              <h2 className="font-display text-3xl font-bold text-white tracking-tight">Real Projects by Real Interns</h2>
              <p className="text-gray-400 text-sm">A look at what interns have designed, built, and shipped at SpacePoint</p>
            </div>

            <div className="flex flex-wrap justify-center gap-4 lg:gap-6 w-full">
              {PROJECTS.map((p, i) => {
                const open = openProject === i;
                return (
                  <button
                    key={p.title}
                    onClick={() => setOpenProject(open ? null : i)}
                    className={`aspect-[4/3] w-full sm:w-[calc(50%-0.5rem)] lg:w-[calc(33.333%-1rem)] rounded-2xl overflow-hidden ${GLASS} group relative shadow-lg transform hover:-translate-y-1 hover:shadow-space-accent/20 hover:shadow-2xl transition-all duration-300 text-left`}
                  >
                    <img
                      src={p.image}
                      onError={(e) => { e.currentTarget.style.display = "none"; }}
                      alt={p.title}
                      className="absolute inset-0 w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                    />
                    <div className="absolute inset-x-0 bottom-0 p-4 bg-gradient-to-t from-black/80 to-transparent">
                      <div className="text-white font-semibold text-sm">{p.title}</div>
                      <div className="text-space-accent text-xs">{p.student}</div>
                      {open && <div className="text-gray-300 text-xs mt-2 leading-relaxed">{p.description}</div>}
                    </div>
                  </button>
                );
              })}
            </div>
          </section>

          {/* SUCCESS STORIES / ALUMNI */}
          <section className="w-full space-y-8">
            <div className="text-center space-y-3">
              <h2 className="font-display text-3xl font-bold text-white tracking-tight">Success Stories</h2>
              <p className="text-gray-400 text-sm max-w-2xl mx-auto">
                Our internship program has helped students continue their journeys with leading organizations in the
                space and advanced technology sectors.
              </p>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4 lg:gap-6">
              {ALUMNI.map((a) => (
                <a
                  key={a.name}
                  href={a.linkedin}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={`${GLASS} rounded-2xl overflow-hidden group hover:border-space-accent/30 transition-all`}
                >
                  {a.photo ? (
                    <img
                      src={a.photo}
                      alt={a.name}
                      loading="lazy"
                      className="w-full aspect-square object-cover group-hover:scale-105 transition-transform duration-500"
                    />
                  ) : (
                    <div className="w-full aspect-square flex items-center justify-center bg-space-accent/10 text-space-accent font-display font-black text-3xl">
                      {a.name.split(" ").map((w) => w[0]).join("")}
                    </div>
                  )}
                  <div className="p-4 space-y-1">
                    <div className="text-white font-semibold text-sm">{a.name}</div>
                    <div className="text-xs text-gray-400">{a.field}</div>
                    <div className="text-xs text-space-accent font-semibold">{a.role}</div>
                  </div>
                </a>
              ))}
            </div>

            <div className="space-y-4 pt-4">
              <p className="text-gray-400 text-sm text-center">
                Previous interns have gone on to opportunities at organizations including:
              </p>
              <div className="flex flex-wrap justify-center gap-3">
                {DESTINATION_ORGS.map((o) => (
                  <span key={o} className={`${GLASS} px-4 py-2 rounded-full text-sm text-gray-300`}>{o}</span>
                ))}
              </div>
              <p className="text-gray-400 text-sm text-center max-w-2xl mx-auto">
                While we are proud of these outcomes, they reflect the interns' own dedication and commitment. Our
                role is to provide the environment, mentorship, and opportunities that allow motivated students to
                excel.
              </p>
            </div>
          </section>

          {/* WHAT WE LOOK FOR + FAQ */}
          <section className="w-full max-w-4xl space-y-12">
            <div className="space-y-8">
              <div className="text-center space-y-3">
                <h2 className="font-display text-3xl font-bold text-white tracking-tight">What We Look For</h2>
                <p className="text-gray-400 text-sm">We value curiosity more than experience</p>
              </div>
              <div className="flex flex-wrap justify-center gap-3">
                {WHAT_WE_LOOK_FOR.map((w) => (
                  <div key={w} className={`${GLASS} px-4 py-3 rounded-full text-sm text-gray-300 flex items-center gap-2`}>
                    <svg className="w-4 h-4 text-space-accent shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    {w}
                  </div>
                ))}
              </div>
            </div>

            <div className="space-y-8">
              <div className="text-center space-y-3">
                <h2 className="font-display text-3xl font-bold text-white tracking-tight">Frequently Asked Questions</h2>
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
            </div>
          </section>

          {/* CLOSING CTA + TEAM QUOTE */}
          <section className="w-full max-w-4xl">
            <div className={`${GLASS} p-8 sm:p-10 rounded-2xl space-y-6 text-center`}>
              <h2 className="font-display text-3xl font-bold text-white tracking-tight">Join Us</h2>
              <p className="text-gray-300 text-base leading-relaxed max-w-2xl mx-auto">
                Whether your passion is satellites, AI, embedded systems, robotics, or advanced engineering,
                SpacePoint offers an opportunity to work on meaningful projects that bridge education, research, and
                industry.
              </p>
              <p className="text-white font-display font-bold text-xl">
                Build real technology. Solve real problems. Shape the future.
              </p>
              <div className="flex justify-center">
                <Link
                  to="/apply/intern"
                  className="w-full sm:w-auto inline-flex items-center justify-center px-8 py-4 rounded-xl font-bold tracking-wide text-space-900 bg-space-accent hover:bg-space-hover transition-all transform hover:-translate-y-0.5 shadow-[0_0_20px_rgba(167,125,255,0.4)]"
                >
                  Apply Today
                  <svg className="w-5 h-5 ml-2 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                  </svg>
                </Link>
              </div>
              <blockquote className="text-left italic text-gray-400 text-sm border-l-2 border-space-accent pl-4 max-w-2xl mx-auto">
                "An internship at SpacePoint isn't about completing a checklist, it's about developing the mindset of
                an engineer. We don't measure success by the number of tasks completed, but by how much you've
                grown, challenged yourself, and contributed to solving real-world problems."
                <footer className="mt-2 not-italic text-gray-500">— The SpacePoint Team</footer>
              </blockquote>
            </div>
          </section>
        </div>
      </div>

      <SiteFooter />
    </div>
  );
}

export default InternsLanding;
