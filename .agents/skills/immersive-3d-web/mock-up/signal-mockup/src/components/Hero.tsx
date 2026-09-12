import { useRef } from "react";
import { HeroScene } from "../three/HeroScene";

export function Hero() {
  const heroRef = useRef<HTMLElement | null>(null);

  return (
    <section
      id="top"
      ref={heroRef}
      className="relative flex min-h-screen w-full items-end overflow-hidden bg-void"
    >
      <div className="absolute inset-0">
        <HeroScene pinTargetRef={heroRef} />
      </div>

      {/* Watermark: breathing background mark */}
      <div
        aria-hidden
        className="logo-watermark pointer-events-none absolute top-1/2 left-1/2 font-display text-[42vw] leading-none font-bold text-mist select-none"
      >
        S
      </div>

      {/* Aurora blobs */}
      <div
        aria-hidden
        className="aurora-blob aurora-1 pointer-events-none"
        style={{ width: "50%", height: "60%", top: "-15%", left: "-10%", background: "radial-gradient(circle, rgba(79,140,255,0.16), transparent 65%)" }}
      />
      <div
        aria-hidden
        className="aurora-blob aurora-2 pointer-events-none"
        style={{ width: "45%", height: "55%", top: "-5%", right: "-8%", background: "radial-gradient(circle, rgba(185,140,255,0.13), transparent 65%)" }}
      />

      <div aria-hidden className="pointer-events-none absolute inset-0 bg-gradient-to-t from-void via-void/40 to-transparent" />
      <div aria-hidden className="pointer-events-none absolute inset-0 bg-gradient-to-r from-void/70 via-transparent to-void/30" />

      <div aria-hidden className="pointer-events-none absolute inset-0 hidden md:block">
        <div className="absolute top-0 left-1/4 h-full w-px bg-line" />
        <div className="absolute top-0 left-1/2 h-full w-px bg-line" />
        <div className="absolute top-0 left-3/4 h-full w-px bg-line" />
      </div>

      <div
        className="glass-card reveal reveal-visible absolute top-[16vh] right-6 hidden w-[190px] rounded-2xl p-4 sm:right-12 md:block"
      >
        <p className="font-mono text-[11px] font-semibold tracking-[0.18em] text-good uppercase">All systems normal</p>
        <p className="font-display mt-2 text-[17px] leading-snug text-mist">
          99.98% <span className="text-signal italic">uptime</span>
        </p>
        <p className="mt-2 text-[11px] leading-relaxed text-dim">Across 240 monitored endpoints this month.</p>
      </div>

      <div className="stagger relative z-10 w-full max-w-3xl px-6 pt-32 pb-16 md:px-16 md:pb-24">
        <p className="mb-4 text-[11px] font-semibold tracking-[0.3em] text-signal uppercase">
          Uptime &amp; incident monitoring
        </p>

        <h1 className="font-display text-[clamp(2.75rem,7vw,5.5rem)] leading-[0.98] font-bold tracking-tight text-mist">
          Know before
          <br />
          <span className="text-gradient-animated">your customers do.</span>
        </h1>

        <p className="mt-6 max-w-md text-[clamp(0.95rem,1.4vw,1.15rem)] font-light text-dim">
          SIGNAL watches your endpoints every 30 seconds from six regions
          and pages the right person in under a minute — no dashboards to
          babysit, no false alarms at 3am.
        </p>

        <div className="pointer-events-none mt-9 flex flex-wrap items-center gap-4">
          <a
            href="#pricing"
            className="hero-cta pointer-events-auto rounded-full bg-signal px-7 py-3 text-xs font-semibold tracking-[0.14em] text-void uppercase transition-transform hover:scale-[1.02] active:scale-[0.97] focus-visible:scale-[1.02] focus-visible:outline-none"
          >
            Start free — no card
          </a>
          <a
            href="#product"
            className="btn-sheen pointer-events-auto rounded-full border border-line px-7 py-3 text-xs tracking-[0.14em] text-mist uppercase transition-colors hover:border-signal focus-visible:border-signal focus-visible:outline-none"
          >
            See it live
          </a>
        </div>

        <p className="mt-8 font-mono text-[11px] tracking-[0.1em] text-dim/70">
          Trusted by 1,200+ engineering teams · SOC 2 in progress
        </p>
      </div>
    </section>
  );
}
