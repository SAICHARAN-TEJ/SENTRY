import { useInViewReveal } from "../hooks/useInViewReveal";

export function Footer() {
  const { ref, className } = useInViewReveal<HTMLDivElement>();

  return (
    <footer id="membership" className="border-t border-line bg-void px-6 py-20 md:px-16 md:py-28">
      <div ref={ref} className={`${className} mx-auto flex max-w-5xl flex-col items-start justify-between gap-10 md:flex-row md:items-end`}>
        <div>
          <p className="text-[11px] font-semibold tracking-[0.3em] text-gold uppercase">Membership</p>
          <h2 className="font-display mt-4 max-w-md text-[clamp(1.75rem,3.5vw,2.75rem)] leading-tight text-star">
            Twelve nights a year, always under a clear sky.
          </h2>
        </div>

        <a
          href="mailto:reservations@apogee.example"
          className="btn-sheen shrink-0 rounded-full bg-gold px-8 py-3 text-xs font-semibold tracking-[0.14em] text-void uppercase transition-transform hover:scale-[1.02] active:scale-[0.97] focus-visible:scale-[1.02] focus-visible:outline-none"
        >
          Join the waitlist
        </a>
      </div>

      <div className="mx-auto mt-20 flex max-w-5xl flex-col-reverse items-start justify-between gap-4 border-t border-line pt-8 text-[11px] tracking-[0.1em] text-star/40 md:flex-row md:items-center">
        <p>© 2026 Apogee Observatory Experiences.</p>
        <p>This is a design mock-up, not a real product.</p>
      </div>
    </footer>
  );
}
