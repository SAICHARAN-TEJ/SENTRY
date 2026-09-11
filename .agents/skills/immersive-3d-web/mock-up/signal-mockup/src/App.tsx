import { CustomCursor } from "./components/CustomCursor";
import { Navbar } from "./components/Navbar";
import { Hero } from "./components/Hero";
import { StatusTicker } from "./components/StatusTicker";
import { KPISection } from "./components/KPISection";
import { Pricing } from "./components/Pricing";
import { Footer } from "./components/Footer";

function App() {
  return (
    <div className="min-h-screen bg-void selection:bg-signal selection:text-void">
      <CustomCursor />
      <Navbar />
      <main>
        <Hero />
        <StatusTicker />
        <KPISection />
        <Pricing />
      </main>
      <Footer />
    </div>
  );
}

export default App;
