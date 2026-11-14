import { Film, Play } from "lucide-react";

export function ResultsPanel({ job }) {
  return (
    <section className="card results-card">
      <div className="card-heading"><div><span className="step">02</span><h2>Your clips</h2></div>{job?.results?.length ? <span className="result-count">{job.results.length} ready</span> : null}</div>
      {job ? <Progress job={job} /> : <EmptyState />}
      {job?.results?.map((clip, index) => <article className="clip-row" key={clip.file}><div className="clip-icon"><Film size={18} /></div><div className="clip-details"><strong>{clip.title_suggestion || `Clip ${index + 1}`}</strong><span>{Number(clip.duration || 0).toFixed(1)} seconds <i>·</i> Score {Number(clip.score || 0).toFixed(2)}</span></div><a className="watch-button" href={clip.url} target="_blank" rel="noreferrer"><Play size={15} fill="currentColor" /> Watch</a></article>)}
      {job?.log?.length ? <details className="activity"><summary>Activity log</summary><pre>{job.log.join("\n")}</pre></details> : null}
    </section>
  );
}

function EmptyState() {
  return <div className="empty-state"><div className="empty-icon"><Film size={30} /></div><h3>Your clips will appear here</h3><p>Configure your source and settings, then create your first batch.</p></div>;
}

function Progress({ job }) {
  const completed = job.status === "done";
  const failed = job.status === "failed";
  return <div className="progress-wrap" aria-live="polite"><div className="progress-label"><span>{failed ? `Failed: ${job.message}` : job.message}</span><strong>{job.progress}%</strong></div><div className="progress-track"><div style={{ width: `${job.progress}%` }} /></div>{completed && <div className="success-message">Your clips are ready to review.</div>}</div>;
}
