import { useLayoutEffect, useRef, type ReactNode } from "react";
import { CalendarIcon, CheckIcon, ClockIcon, DocumentIcon, MapPinIcon, VideoIcon } from "../../../../shared/ui/icons";

/** How long each card rests at the front, and how long the ring takes to
 * bring the next one round. Long enough to read a card; short enough that
 * the ring is visibly turning while someone reads the copy beside it. */
const DWELL_MS = 3000;
const TURN_MS = 1100;

/** Dates on the cards are counted from today, so a schedule on the page
 * never shows a day that has already gone by. */
function daysFromNow(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
}

function easeInOut(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

/**
 * The applicant's side of the system, as a ring of the screens they
 * actually meet — the tracker, an examination to confirm, an interview
 * already confirmed, an offer, their documents — turning slowly so one
 * faces front at a time and the rest sit behind it at depth.
 *
 * Driven from script rather than a CSS spin so the cards travel a true
 * ellipse, keep their text upright and crisp when they come to rest, and
 * dim with distance without turning see-through. It pauses under the
 * pointer, off screen, and entirely for anyone who has asked for reduced
 * motion.
 */
export function ApplicationOrbit() {
  const stageRef = useRef<HTMLDivElement>(null);
  const cardRefs = useRef<(HTMLDivElement | null)[]>([]);

  useLayoutEffect(() => {
    const stage = stageRef.current;
    const cards = cardRefs.current.filter((c): c is HTMLDivElement => c !== null);
    if (!stage || cards.length === 0) return;

    const step = (2 * Math.PI) / cards.length;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let radiusX = 200;
    let clock = 0;
    let last = 0;
    let raf = 0;
    let hovering = false;
    let onScreen = true;

    // `turn` counts cards: 0 has card 0 in front, 1 has card 1, and so on.
    function place(turn: number) {
      cards.forEach((card, i) => {
        const theta = (i - turn) * step;
        const depth = (Math.cos(theta) + 1) / 2; // 1 in front, 0 at the back
        const x = Math.sin(theta) * radiusX;
        const y = -(1 - depth) * 46; // the far side sits higher: a ring seen from just above
        const scale = 0.62 + 0.38 * depth;
        const tilt = Math.sin(theta) * 22;
        card.style.transform = `translate(-50%, -50%) translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0) rotateY(${tilt.toFixed(2)}deg) scale(${scale.toFixed(3)})`;
        card.style.zIndex = String(Math.round(depth * 100));
        card.style.setProperty("--dim", ((1 - depth) * 0.72).toFixed(3));
      });
    }

    function turnAt(t: number): number {
      const cycle = DWELL_MS + TURN_MS;
      const k = Math.floor(t / cycle);
      const p = Math.min(1, Math.max(0, (t - k * cycle - DWELL_MS) / TURN_MS));
      return k + easeInOut(p);
    }

    function frame(now: number) {
      // Capped so a stall (a busy main thread, a backgrounded tab) resumes
      // where it left off instead of jumping several cards at once.
      clock += last ? Math.min(now - last, 50) : 0;
      last = now;
      place(turnAt(clock));
      raf = requestAnimationFrame(frame);
    }

    function sync() {
      const shouldRun = !reduceMotion && onScreen && !hovering;
      if (shouldRun && !raf) {
        last = 0;
        raf = requestAnimationFrame(frame);
      } else if (!shouldRun && raf) {
        cancelAnimationFrame(raf);
        raf = 0;
      }
    }

    // The ring's width follows the space it has: the cards' own width
    // is fixed, so on a narrow screen they close up around the front one.
    const resize = new ResizeObserver(() => {
      radiusX = Math.min(200, stage.clientWidth * 0.37);
      place(turnAt(clock));
    });
    resize.observe(stage);

    const visibility = new IntersectionObserver(([entry]) => {
      onScreen = entry.isIntersecting;
      sync();
    });
    visibility.observe(stage);

    const enter = () => { hovering = true; sync(); };
    const leave = () => { hovering = false; sync(); };
    stage.addEventListener("pointerenter", enter);
    stage.addEventListener("pointerleave", leave);

    place(0);
    sync();

    return () => {
      cancelAnimationFrame(raf);
      resize.disconnect();
      visibility.disconnect();
      stage.removeEventListener("pointerenter", enter);
      stage.removeEventListener("pointerleave", leave);
    };
  }, []);

  const cards: ReactNode[] = [
    <TrackerCard key="tracker" />,
    <ExamCard key="exam" />,
    <InterviewCard key="interview" />,
    <OfferCard key="offer" />,
    <DocumentsCard key="documents" />,
  ];

  return (
    // A picture of the product, not part of this page's controls: hidden
    // from assistive technology, and nothing in it can take focus.
    <div ref={stageRef} className="ark-orbit" aria-hidden="true">
      {cards.map((card, i) => (
        <div
          key={i}
          ref={(el) => {
            cardRefs.current[i] = el;
          }}
          className="ark-orbit__card"
        >
          {card}
        </div>
      ))}
    </div>
  );
}

function CardHead({ stage, title, department }: { stage: string; title: string; department: string }) {
  return (
    <div className="ark-orbit__head">
      <span className="ark-orbit__stage">{stage}</span>
      <span className="ark-orbit__title">{title}</span>
      <span className="ark-orbit__dept">{department}</span>
    </div>
  );
}

function InfoRow({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="ark-orbit__row">
      <span className="ark-orbit__row-icon">{icon}</span>
      <span>
        <span className="ark-orbit__row-label">{label}</span>
        <span className="ark-orbit__row-value">{value}</span>
      </span>
    </div>
  );
}

function TrackerCard() {
  const steps: Array<{ label: string; state: "done" | "current" | "todo" }> = [
    { label: "Application submitted", state: "done" },
    { label: "Pre-screening", state: "done" },
    { label: "Examination", state: "current" },
    { label: "Interviews", state: "todo" },
    { label: "Final decision", state: "todo" },
  ];
  return (
    <>
      <div className="ark-tracker__head">
        <div>
          <span className="ark-tracker__eyebrow">Library Services</span>
          <span className="ark-tracker__title">Library Assistant</span>
        </div>
        <span className="ark-tracker__count">3 of 5</span>
      </div>
      <div className="ark-tracker__bar">
        <span style={{ width: "50%" }} />
      </div>
      <ol className="ark-tracker__steps">
        {steps.map((s) => (
          <li key={s.label} data-state={s.state}>
            <span className="ark-tracker__node">{s.state === "done" && <CheckIcon width={11} height={11} strokeWidth={3} />}</span>
            <span className="ark-tracker__label">{s.label}</span>
            {s.state === "current" && <span className="ark-tracker__now">You are here</span>}
          </li>
        ))}
      </ol>
    </>
  );
}

function ExamCard() {
  return (
    <>
      <CardHead stage="Examination" title="Software Engineer I" department="Computing" />
      <div className="ark-orbit__rows">
        <InfoRow icon={<CalendarIcon width={15} height={15} />} label="Date" value={daysFromNow(6)} />
        <InfoRow icon={<ClockIcon width={15} height={15} />} label="Time" value="9:00 AM – 11:00 AM" />
        <InfoRow icon={<MapPinIcon width={15} height={15} />} label="Location" value="Computer Laboratory 2" />
      </div>
      <div className="ark-orbit__ask">
        <span className="ark-orbit__ask-q">Are you available at this time?</span>
        <span className="ark-orbit__btns">
          <span className="ark-btn ark-btn--primary ark-btn--sm">Yes, I can attend</span>
          <span className="ark-btn ark-btn--outline ark-btn--sm">I'm not available</span>
        </span>
      </div>
    </>
  );
}

function InterviewCard() {
  return (
    <>
      <CardHead stage="Interview Round 1" title="English Professor" department="Liberal Arts" />
      <div className="ark-orbit__rows">
        <InfoRow icon={<CalendarIcon width={15} height={15} />} label="Date" value={daysFromNow(9)} />
        <InfoRow icon={<ClockIcon width={15} height={15} />} label="Time" value="2:00 PM" />
        <InfoRow icon={<VideoIcon width={15} height={15} />} label="Meeting" value="Online (link from HR)" />
      </div>
      <div className="ark-orbit__note">
        <CheckIcon width={15} height={15} />
        You've confirmed you're available. Nothing more to do. See you then.
      </div>
    </>
  );
}

function OfferCard() {
  return (
    <>
      <span className="ark-orbit__badge">
        <CheckIcon width={11} height={11} strokeWidth={3} />
        You've been accepted
      </span>
      <span className="ark-orbit__offer-title">Congratulations, we'd like you to join us.</span>
      <p className="ark-orbit__text">
        MSEUF is offering you the position of <b>Reference Librarian</b> in Library Services.
      </p>
      <div className="ark-orbit__countdown">
        <ClockIcon width={15} height={15} />
        4 days, 6 hours left to respond
      </div>
      <span className="ark-orbit__btns">
        <span className="ark-btn ark-btn--primary ark-btn--sm">Accept Offer</span>
        <span className="ark-btn ark-btn--outline ark-btn--sm">Decline</span>
      </span>
    </>
  );
}

function DocumentsCard() {
  const files: Array<[string, string]> = [
    ["Resume.pdf", "248 KB"],
    ["Letter of Intent.pdf", "96 KB"],
    ["Transcript of Records.pdf", "1.2 MB"],
  ];
  return (
    <>
      <CardHead stage="Document Upload" title="Data Science Professor" department="CCMS" />
      <div className="ark-orbit__files">
        {files.map(([name, size]) => (
          <div key={name} className="ark-orbit__file">
            <span className="ark-orbit__file-icon">
              <DocumentIcon width={15} height={15} />
            </span>
            <span className="ark-orbit__file-name">{name}</span>
            <span className="ark-orbit__file-size">{size}</span>
            <CheckIcon width={14} height={14} className="ark-orbit__file-ok" />
          </div>
        ))}
      </div>
      <div className="ark-orbit__done">
        <CheckIcon width={13} height={13} strokeWidth={3} />
        Submitted. Up next: Pre-screening
      </div>
    </>
  );
}
