import { useState } from "react";

const LINKS = ["Experiences", "The Sky", "Membership", "Journal"];

export function Navbar() {
  const [open, setOpen] = useState(false);

  return (
    <header className="fixed top-0 left-0 z-50 w-full bg-gradient-to-b from-void/90 via-void/50 to-transparent backdrop-blur-[2px]">
      <div className="flex items-center justify-between px-6 py-5 md:px-12 md:py-7">
        <a href="#top" className="font-display flex items-center gap-2 text-xl tracking-[0.08em] text-star italic">
          Apogee
        </a>

        <nav className="hidden items-center gap-9 md:flex">
          {LINKS.map((link) => (
            <a
              key={link}
              href={`#${link.toLowerCase().replace(" ", "-")}`}
              className="nav-link text-xs tracking-[0.14em] text-star/60 uppercase transition-colors hover:text-star focus-visible:text-star focus-visible:outline-none"
            >
              {link}
            </a>
          ))}
        </nav>

        <a
          href="#experiences"
          className="btn-sheen hidden rounded-full border border-line px-5 py-2 text-xs tracking-[0.14em] text-star uppercase transition-colors hover:border-gold md:inline-block"
        >
          Reserve a session
        </a>

        <button
          type="button"
          aria-label="Toggle menu"
          onClick={() => setOpen((v) => !v)}
          className="flex h-9 w-9 flex-col items-center justify-center gap-1.5 md:hidden"
        >
          <span className={`h-px w-5 bg-star transition-transform ${open ? "translate-y-[3.5px] rotate-45" : ""}`} />
          <span className={`h-px w-5 bg-star transition-transform ${open ? "-translate-y-[3.5px] -rotate-45" : ""}`} />
        </button>
      </div>

      {open && (
        <div className="flex flex-col items-center gap-6 bg-void/98 py-10 backdrop-blur-md md:hidden">
          {LINKS.map((link) => (
            <a
              key={link}
              href={`#${link.toLowerCase().replace(" ", "-")}`}
              onClick={() => setOpen(false)}
              className="text-sm tracking-[0.14em] text-star/80 uppercase"
            >
              {link}
            </a>
          ))}
        </div>
      )}
    </header>
  );
}
