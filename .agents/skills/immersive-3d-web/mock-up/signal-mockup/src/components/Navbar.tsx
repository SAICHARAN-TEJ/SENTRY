import { useState } from "react";

const LINKS = ["Product", "Status", "Pricing", "Docs"];

export function Navbar() {
  const [open, setOpen] = useState(false);

  return (
    <header className="fixed top-0 left-0 z-50 w-full bg-gradient-to-b from-void/90 via-void/50 to-transparent backdrop-blur-[2px]">
      <div className="flex items-center justify-between px-6 py-5 md:px-12 md:py-7">
        <a href="#top" className="font-display flex items-center gap-2 text-lg font-semibold tracking-tight text-mist">
          <span className="h-2 w-2 rounded-full bg-good shadow-[0_0_8px_2px_rgba(61,220,132,0.6)]" />
          SIGNAL
        </a>

        <nav className="hidden items-center gap-9 md:flex">
          {LINKS.map((link) => (
            <a
              key={link}
              href={`#${link.toLowerCase()}`}
              className="nav-link text-xs tracking-[0.14em] text-dim uppercase transition-colors hover:text-mist focus-visible:text-mist focus-visible:outline-none"
            >
              {link}
            </a>
          ))}
        </nav>

        <a
          href="#pricing"
          className="btn-sheen hidden rounded-full border border-line px-5 py-2 text-xs tracking-[0.14em] text-mist uppercase transition-colors hover:border-signal md:inline-block"
        >
          Start monitoring
        </a>

        <button
          type="button"
          aria-label="Toggle menu"
          onClick={() => setOpen((v) => !v)}
          className="flex h-9 w-9 flex-col items-center justify-center gap-1.5 md:hidden"
        >
          <span className={`h-px w-5 bg-mist transition-transform ${open ? "translate-y-[3.5px] rotate-45" : ""}`} />
          <span className={`h-px w-5 bg-mist transition-transform ${open ? "-translate-y-[3.5px] -rotate-45" : ""}`} />
        </button>
      </div>

      {open && (
        <div className="flex flex-col items-center gap-6 bg-void/98 py-10 backdrop-blur-md md:hidden">
          {LINKS.map((link) => (
            <a
              key={link}
              href={`#${link.toLowerCase()}`}
              onClick={() => setOpen(false)}
              className="text-sm tracking-[0.14em] text-mist/80 uppercase"
            >
              {link}
            </a>
          ))}
        </div>
      )}
    </header>
  );
}
