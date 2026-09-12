import { Tilt } from "./Tilt";
import { useInViewReveal } from "../hooks/useInViewReveal";

const TIERS = [
  {
    name: "Starter",
    price: "Free",
    desc: "5 monitors, 5-minute checks, email alerts.",
    cta: "Start free",
    recommended: false,
  },
  {
    name: "Pro",
    price: "$29/mo",
    desc: "Unlimited monitors, 30-second checks, SMS + Slack + PagerDuty.",
    cta: "Start free trial",
    recommended: true,
  },
];

function TierCard({ tier, index }: { tier: (typeof TIERS)[number]; index: number }) {
  const { ref, className } = useInViewReveal<HTMLDivElement>();

  return (
    <div ref={ref} className={className} style={{ transitionDelay: `${index * 0.1}s` }}>
      <Tilt max={5}>
        {/* Hover-only mask-composite overlay: the card's own background
            stays real/opaque, the gradient ring only appears on hover —
            see immersive-3d-web skill, state-and-feedback.md. */}
        <div className={`glow-ring lift-card rounded-2xl border p-8 ${tier.recommended ? "selected border-signal/30 bg-panel" : "border-line bg-panel"}`}>
          {tier.recommended && (
            <span className="font-mono mb-4 inline-block rounded-full bg-signal/15 px-3 py-1 text-[10px] font-semibold tracking-[0.14em] text-signal uppercase">
              Recommended
            </span>
          )}
          <h3 className="font-display text-xl text-mist">{tier.name}</h3>
          <p className="font-mono mt-2 text-3xl font-semibold text-mist">{tier.price}</p>
          <p className="mt-4 text-sm leading-relaxed text-dim">{tier.desc}</p>
          <a
            href="#top"
            className="btn-sheen mt-8 inline-block w-full rounded-full bg-signal px-6 py-3 text-center text-xs font-semibold tracking-[0.14em] text-void uppercase transition-transform hover:scale-[1.01] active:scale-[0.97]"
          >
            {tier.cta}
          </a>
        </div>
      </Tilt>
    </div>
  );
}

export function Pricing() {
  const heading = useInViewReveal<HTMLDivElement>();
  const locked = useInViewReveal<HTMLDivElement>();

  return (
    <section id="pricing" className="relative border-t border-line bg-void px-6 py-28 md:px-16 md:py-36">
      <div className="mx-auto max-w-5xl">
        <div ref={heading.ref} className={heading.className}>
          <p className="text-[11px] font-semibold tracking-[0.3em] text-signal uppercase">Pricing</p>
          <h2 className="font-display mt-4 max-w-xl text-[clamp(2rem,4.5vw,3.25rem)] leading-tight text-mist">
            Free to start, honest after that.
          </h2>
        </div>

        <div className="mt-16 grid gap-6 md:grid-cols-2">
          {TIERS.map((tier, i) => (
            <TierCard key={tier.name} tier={tier} index={i} />
          ))}
        </div>

        {/* Opaque double-background gradient border — a permanent
            "locked" state for a real, named feature. Not interchangeable
            with .glow-ring above: this box paints its own surface, so an
            opaque padding-box fill is correct here. */}
        <div ref={locked.ref} className={`${locked.className} locked-card lift-card mt-6 flex flex-col items-start justify-between gap-4 rounded-2xl p-6 md:flex-row md:items-center`}>
          <div>
            <span className="font-mono text-[10px] font-semibold tracking-[0.14em] text-violet uppercase">Pro feature · Locked</span>
            <h3 className="font-display mt-2 text-lg text-mist">AI Root Cause Analysis</h3>
            <p className="mt-1 max-w-md text-sm text-dim">Automatically correlates an error spike with the deploy, dependency, or infra change that likely caused it.</p>
          </div>
          <a
            href="#pricing"
            className="nav-link shrink-0 text-xs font-semibold tracking-[0.14em] text-signal uppercase"
          >
            Unlock with Pro →
          </a>
        </div>
      </div>
    </section>
  );
}
