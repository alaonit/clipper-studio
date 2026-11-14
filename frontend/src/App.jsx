import { Clapperboard, Film, Sparkles } from "lucide-react";
import { useState } from "react";
import { DEFAULT_FORM } from "./config";
import { ResultsPanel } from "./components/ResultsPanel";
import { SourceSettings } from "./components/SourceSettings";
import { useClipJob } from "./hooks/useClipJob";

export function App() {
  const [form, setForm] = useState({ ...DEFAULT_FORM });
  const [validationError, setValidationError] = useState("");
  const { job, error, isStarting, start } = useClipJob();

  function submit(event) {
    event.preventDefault();
    if ((!form.file && !form.source.trim()) || form.minimum <= 0 || form.maximum < form.minimum || form.num <= 0) {
      setValidationError("Check the clip count and duration range.");
      return;
    }
    setValidationError("");
    start(form);
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand"><span className="brand-mark"><Clapperboard size={20} /></span><span>Clipper <em>Studio</em></span></div>
        <span className="local-pill"><span /> Running locally</span>
      </header>
      <section className="hero">
        <div><div className="eyebrow"><Sparkles size={15} /> AI-ASSISTED VIDEO EDITING</div><h1>Find the moments<br /><span>worth sharing.</span></h1><p>Turn long-form video into polished, social-ready clips. Everything runs locally on your computer.</p></div>
        <div className="hero-art"><div className="orb orb-one" /><div className="orb orb-two" /><Film size={74} strokeWidth={1} /></div>
      </section>
      <div className="workspace">
        <SourceSettings form={form} onChange={setForm} onSubmit={submit} disabled={isStarting} error={validationError || error} />
        <ResultsPanel job={job} />
      </div>
      <footer>Clipper Studio <span>·</span> Private video processing</footer>
    </main>
  );
}
