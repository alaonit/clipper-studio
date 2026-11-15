import {
  CheckCircle2, Clapperboard, LayoutDashboard, Link2, Menu, Moon,
  PlusCircle, Settings, Sun, Wifi, X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { DEFAULT_FORM } from "./config";
import { ResultsPanel } from "./components/ResultsPanel";
import { SourceSettings } from "./components/SourceSettings";
import {
  checkBackend, clearBackendUrl, fetchJobs, getBackendUrl, setBackendUrl,
  fetchSettings,
} from "./api/jobs";
import { useClipJob } from "./hooks/useClipJob";

const TERMINAL = new Set(["done", "completed", "failed", "cancelled"]);

export function App() {
  const [page, setPage] = useState("dashboard");
  const [dark, setDark] = useState(() => localStorage.getItem("theme") !== "light");
  const [backendUrl, setBackend] = useState(getBackendUrl());
  const [connection, setConnection] = useState("offline");
  const [jobs, setJobs] = useState([]);
  const [connectOpen, setConnectOpen] = useState(false);

  useEffect(() => {
    document.documentElement.classList.toggle("studio-dark", dark);
    localStorage.setItem("theme", dark ? "dark" : "light");
  }, [dark]);

  useEffect(() => {
    if (page !== "dashboard" || !backendUrl) return;
    fetchJobs().then((data) => setJobs(data.jobs || data || [])).catch(() => setJobs([]));
  }, [page, backendUrl]);

  async function connect(value) {
    setBackend(value);
    await checkBackend();
    setBackendUrl(value);
    setConnection("online");
    setConnectOpen(false);
  }

  function disconnect() {
    clearBackendUrl();
    setBackend("");
    setConnection("offline");
  }

  return (
    <div className="studio-app">
      <Sidebar page={page} setPage={setPage} dark={dark} setDark={setDark}
        backendUrl={backendUrl} connection={connection} onConnect={() => setConnectOpen(true)}
        onDisconnect={disconnect} />
      <main className="studio-main">
        <div className="mobile-studio-bar"><Menu size={20} /><strong>Clipper Studio</strong></div>
        {page === "dashboard" && <Dashboard jobs={jobs} connected={connection === "online"} onNew={() => setPage("new")} onConnect={() => setConnectOpen(true)} />}
        {page === "new" && <NewJob onDone={(job) => { setJobs((current) => [job, ...current]); setPage("dashboard"); }} />}
        {page === "settings" && <SettingsPage backendUrl={backendUrl} connected={connection === "online"} onConnect={() => setConnectOpen(true)} />}
      </main>
      {connectOpen && <ConnectModal initial={backendUrl} onClose={() => setConnectOpen(false)} onConnect={connect} />}
    </div>
  );
}

function Sidebar({ page, setPage, dark, setDark, backendUrl, connection, onConnect, onDisconnect }) {
  return <aside className="studio-sidebar">
    <div className="studio-brand"><span className="studio-brand-mark"><Clapperboard size={17} /></span><span>Clipper <em>Studio</em></span>
      <strong>AI Auto-Clipper</strong><small>Remote GPU workflow</small></div>
    <nav>
      <NavItem icon={LayoutDashboard} label="Dashboard" active={page === "dashboard"} onClick={() => setPage("dashboard")} />
      <NavItem icon={PlusCircle} label="New Job" active={page === "new"} onClick={() => setPage("new")} />
      <NavItem icon={Settings} label="Settings" active={page === "settings"} onClick={() => setPage("settings")} />
    </nav>
    <div className="connect-panel">
      <div className="connection-label"><span className={`connection-dot ${connection}`} /><span>{connection === "online" ? "Backend connected" : "Not connected"}</span></div>
      {backendUrl && <small className="backend-url">{backendUrl}</small>}
      <button className="outline-button" onClick={connection === "online" ? onDisconnect : onConnect}>{connection === "online" ? "Disconnect" : "Connect backend"}</button>
      <button className="outline-button theme-button" onClick={() => setDark(!dark)}>{dark ? <Sun size={14} /> : <Moon size={14} />}{dark ? "Light mode" : "Dark mode"}</button>
    </div>
  </aside>;
}

function NavItem({ icon: Icon, label, active, onClick }) {
  return <button className={`studio-nav-item ${active ? "active" : ""}`} onClick={onClick}><Icon size={18} />{label}</button>;
}

function Dashboard({ jobs, connected, onNew, onConnect }) {
  const completed = jobs.filter((job) => job.status === "done" || job.status === "completed").length;
  const clips = jobs.reduce((sum, job) => sum + (job.results?.length || job.clips?.length || 0), 0);
  return <div className="studio-content">
    <header className="page-header"><div><p className="eyebrow">DASHBOARD</p><h1>Overview</h1><p>Monitor your clipping jobs and generated videos.</p></div><button className="studio-primary" onClick={onNew}><PlusCircle size={17} /> New Job</button></header>
    {!connected && <div className="connect-notice"><Wifi size={20} /><div><strong>Backend not connected</strong><p>Connect your Render, local, Kaggle, or Colab backend to load jobs.</p></div><button onClick={onConnect}>Connect</button></div>}
    <div className="stats-grid"><Stat label="Total jobs" value={jobs.length || "—"} /><Stat label="Completed" value={jobs.length ? completed : "—"} /><Stat label="Total clips" value={jobs.length ? clips : "—"} /><Stat label="System" value={connected ? "Online" : "Offline"} /></div>
    <section className="studio-card job-list"><div className="section-title"><h2>Recent jobs</h2><span>{jobs.length} jobs</span></div>
      {jobs.length ? jobs.map((job) => <JobRow key={job.id} job={job} />) : <div className="empty-studio"><Clapperboard size={31} /><h3>No jobs yet</h3><p>Create your first AI clipping job to get started.</p><button className="studio-primary" onClick={onNew}>Create first job</button></div>}
    </section>
  </div>;
}

function Stat({ label, value }) {
  return <div className="studio-card stat-card"><span>{label}</span><strong>{value}</strong></div>;
}

function JobRow({ job }) {
  const status = job.status || "queued";
  const title = job.source || job.url || job.upload_filename || "Untitled video";
  return <div className="job-row"><div className="job-icon"><Clapperboard size={17} /></div><div className="job-info"><strong>{title}</strong><small>{job.id} · {job.message || status}</small></div><span className={`status-badge ${status}`}>{status}</span><span className="job-progress">{job.progress ?? job.progress?.percent ?? 0}%</span></div>;
}

function NewJob({ onDone }) {
  const [form, setForm] = useState({ ...DEFAULT_FORM });
  const [validationError, setValidationError] = useState("");
  const { job, error, isStarting, start } = useClipJob();
  function submit(event) {
    event.preventDefault();
    if (!form.file && !form.source.trim()) return setValidationError("Upload a video or provide a direct video URL.");
    if (form.minimum <= 0 || form.maximum < form.minimum || form.num <= 0) return setValidationError("Check the clip count and duration range.");
    setValidationError("");
    start(form);
  }
  useEffect(() => { if (job && TERMINAL.has(job.status)) onDone(job); }, [job, onDone]);
  return <div className="studio-content narrow"><header className="page-header"><div><p className="eyebrow">NEW JOB</p><h1>Create clipping job</h1><p>Generate short, social-ready clips from a long video.</p></div></header><SourceSettings form={form} onChange={setForm} onSubmit={submit} disabled={isStarting} error={validationError || error} /><ResultsPanel job={job} /></div>;
}

function SettingsPage({ backendUrl, connected, onConnect }) {
  const [settings, setSettings] = useState(null);
  useEffect(() => { if (connected) fetchSettings().then(setSettings).catch(() => setSettings(null)); }, [connected]);
  const features = settings?.features || {};
  return <div className="studio-content narrow"><header className="page-header"><div><p className="eyebrow">SETTINGS</p><h1>Studio settings</h1><p>Configure the backend connection used for clipping jobs.</p></div></header><section className="studio-card settings-page"><h2>Backend connection</h2><div className="settings-status"><span className={`connection-dot ${connected ? "online" : "offline"}`} /><strong>{connected ? "Connected" : "Not connected"}</strong></div><label>Backend URL</label><input className="studio-input" readOnly value={backendUrl || "No backend configured"} /><p className="settings-help">Use your Render API URL, local API URL, or the public HTTPS URL from a Kaggle/Colab notebook.</p><button className="studio-primary" onClick={onConnect}><Link2 size={16} /> Test or change connection</button></section><section className="studio-card settings-page"><h2>Processing capabilities</h2><div className="capability-list"><Capability label="Upload-first processing" enabled /><Capability label="Supabase job persistence" enabled={settings?.supabase_enabled} /><Capability label="Gemini AI" enabled={features.gemini} /><Capability label="Pexels B-roll" enabled={features.broll} /><Capability label="Speaker diarization" enabled={features.diarization} /><Capability label="YouTube publishing" enabled={features.youtube_publish} /></div><p className="settings-help">Face tracking and full voice-over rendering require the reference GPU backend and its isolated dependencies.</p></section></div>;
}

function Capability({ label, enabled }) {
  return <span className={enabled ? "" : "capability-disabled"}>{enabled ? <CheckCircle2 size={16} /> : <X size={16} />}{label}</span>;
}

function ConnectModal({ initial, onClose, onConnect }) {
  const [value, setValue] = useState(initial);
  const [error, setError] = useState("");
  async function submit(event) {
    event.preventDefault();
    try { await onConnect(value); } catch (connectError) { setError(connectError.message); }
  }
  return <div className="modal-backdrop"><form className="connect-modal" onSubmit={submit}><button type="button" className="modal-close" onClick={onClose}><X size={18} /></button><p className="eyebrow">BACKEND CONNECTION</p><h2>Connect your clipping server</h2><p>Paste an HTTPS Render, local, Kaggle, or Colab backend URL. The URL is saved only in this browser.</p><label>Backend URL</label><input className="studio-input" autoFocus required value={value} onChange={(event) => setValue(event.target.value)} placeholder="https://your-backend.example.com" />{error && <div className="error">{error}</div>}<button className="studio-primary" type="submit"><Wifi size={16} /> Test & connect</button></form></div>;
}
