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

      <div
        aria-hidden
        className="logo-watermark pointer-events-none absolute top-1/2 left-1/2 font-display text-[38vw] leading-none text-star italic select-none"
        style={{ transform: "translate(-50%, -50%)" }}
      >
        A
      </div>

      <div
        aria-hidden
        className="pointer-events-none absolute top-[-10%] left-1/2 h-[45vh] w-[70vw] -translate-x-1/2 rounded-full"
        style={{ background: "radial-gradient(circle, rgba(124,107,214,0.14), transparent 65%)" }}
      />

      <div aria-hidden className="pointer-events-none absolute inset-0 bg-gradient-to-t from-void via-void/40 to-transparent" />
      <div aria-hidden className="pointer-events-none absolute inset-0 bg-gradient-to-r from-void/70 via-transparent to-void/30" />

      <div aria-hidden className="pointer-events-none absolute inset-0 hidden md:block">
        <div className="absolute top-0 left-1/4 h-full w-px bg-line" />
        <div className="absolute top-0 left-1/2 h-full w-px bg-line" />
        <div className="absolute top-0 left-3/4 h-full w-px bg-line" />
      </div>

      <div className="glass-card animate-fade-up absolute top-[16vh] right-6 hidden w-[190px] rounded-2xl p-4 opacity-0 sm:right-12 md:block" style={{ animationDelay: "0.15s" }}>
        <p className="font-mono text-[11px] font-semibold tracking-[0.14em] text-gold uppercase">Tonight</p>
        <p className="font-display mt-2 text-[18px] leading-snug text-star">
          Clear skies, <span className="text-gold italic">98% visibility</span>
        </p>
        <p className="mt-2 text-[11px] leading-relaxed text-star/55">Saturn's rings resolve well after 10pm from the west deck.</p>
      </div>

      <div className="relative z-10 w-full max-w-3xl px-6 pt-32 pb-16 md:px-16 md:pb-24">
        <p className="animate-fade-up mb-4 text-[11px] font-semibold tracking-[0.3em] text-gold uppercase opacity-0" style={{ animationDelay: "0.05s" }}>
          Private observatory experiences
        </p>

        <h1 className="animate-fade-up font-display text-[clamp(2.75rem,7vw,5.5rem)] leading-[1] text-star opacity-0" style={{ animationDelay: "0.2s" }}>
          The sky, without
          <br />
          <span className="text-gold italic">the city in the way.</span>
        </h1>

        <p className="animate-fade-up mt-6 max-w-md text-[clamp(0.95rem,1.4vw,1.15rem)] font-light text-star/65 opacity-0" style={{ animationDelay: "0.35s" }}>
          A private dome, a research-grade telescope, and someone who
          actually knows what you're looking at — two hours from the
          nearest streetlight, forty minutes from your hotel.
        </p>

        <div className="pointer-events-none mt-9 flex flex-wrap items-center gap-4 opacity-0 animate-fade-up" style={{ animationDelay: "0.5s" }}>
          <a
            href="#experiences"
            className="hero-cta pointer-events-auto rounded-full bg-gold px-7 py-3 text-xs font-semibold tracking-[0.14em] text-void uppercase transition-transform hover:scale-[1.02] active:scale-[0.97] focus-visible:scale-[1.02] focus-visible:outline-none"
          >
            Reserve a session
          </a>
          <a
            href="#the-sky"
            className="btn-sheen pointer-events-auto rounded-full border border-star/25 px-7 py-3 text-xs tracking-[0.14em] text-star uppercase transition-colors hover:border-gold focus-visible:border-gold focus-visible:outline-none"
          >
            What's visible tonight
          </a>
        </div>

        <p className="animate-fade-up mt-8 font-mono text-[11px] tracking-[0.1em] text-star/40 opacity-0" style={{ animationDelay: "0.65s" }}>
          34.5°S 71.2°W · Elevation 2,180m · Bortle class 1
        </p>
      </div>
    </section>
  );
}
