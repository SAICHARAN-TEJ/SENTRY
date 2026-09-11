import { CustomCursor } from "./components/CustomCursor";
import { Navbar } from "./components/Navbar";
import { Hero } from "./components/Hero";
import { Experiences } from "./components/Experiences";
import { TheSky } from "./components/TheSky";
import { Footer } from "./components/Footer";

function App() {
  return (
    <div className="min-h-screen bg-void selection:bg-gold selection:text-void">
      <CustomCursor />
      <Navbar />
      <main>
        <Hero />
        <Experiences />
        <TheSky />
      </main>
      <Footer />
    </div>
  );
}

export default App;
