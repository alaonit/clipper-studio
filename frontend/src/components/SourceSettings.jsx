import { FolderOpen, LoaderCircle, Play, Upload } from "lucide-react";
import { MODEL_OPTIONS } from "../config";

export function SourceSettings({ form, onChange, onSubmit, disabled, error }) {
  const update = (field, value) => onChange({ ...form, [field]: value });
  return (
    <form className="card settings-card" onSubmit={onSubmit}>
      <div className="card-heading"><div><span className="step">01</span><h2>Source & settings</h2></div><span className="required">Required</span></div>
      <label>Video source <span>Upload a file or paste a direct URL</span></label>
      <label className="upload-button"><Upload size={17} /> Upload a video<input type="file" accept="video/*" onChange={(event) => update("file", event.target.files?.[0] || null)} /></label>
      {form.file && <div className="upload-name">{form.file.name}</div>}
      <input className="text-input" value={form.source} onChange={(event) => update("source", event.target.value)} placeholder="https://... direct video URL" required={!form.file} />
      <label>Output folder</label>
      <div className="input-with-icon"><FolderOpen size={17} /><input className="text-input" value={form.output} onChange={(event) => update("output", event.target.value)} /></div>
      <div className="field-grid">
        <NumberField label="Number of clips" value={form.num} onChange={(value) => update("num", value)} />
        <SelectField label="Whisper model" value={form.model} onChange={(value) => update("model", value)} options={MODEL_OPTIONS} />
        <NumberField label="Minimum duration" suffix="sec" value={form.minimum} onChange={(value) => update("minimum", value)} />
        <NumberField label="Maximum duration" suffix="sec" value={form.maximum} onChange={(value) => update("maximum", value)} />
        <SelectField label="Aspect ratio" value={form.aspectRatio} onChange={(value) => update("aspectRatio", value)} options={["9:16", "16:9", "1:1", "3:4", "4:5"]} />
        <SelectField label="Font style" value={form.fontStyle} onChange={(value) => update("fontStyle", value)} options={["HORMOZI", "DEFAULT", "STORYTELLER", "CINEMATIC"]} />
        <SelectField label="AI provider" value={form.aiProvider} onChange={(value) => update("aiProvider", value)} options={["gemini", "nvidia"]} />
        <SelectField label="Device" value={form.device} onChange={(value) => update("device", value)} options={["auto", "cuda", "cpu"]} />
      </div>
      <label>Video format</label>
      <div className="segmented">
        <button type="button" className={form.format === "vertical" ? "selected" : ""} onClick={() => update("format", "vertical")}>Vertical <small>9:16</small></button>
        <button type="button" className={form.format === "original" ? "selected" : ""} onClick={() => update("format", "original")}>Original <small>Source</small></button>
      </div>
      <label className="check-label"><input type="checkbox" checked={form.captions} onChange={(event) => update("captions", event.target.checked)} /><span>Burn in captions</span><small>Word-timed subtitles</small></label>
      <label className="upload-button"><MusicIcon /> Add background music<input type="file" accept="audio/*" onChange={(event) => update("bgmFile", event.target.files?.[0] || null)} /></label>
      {form.bgmFile && <div className="upload-name">{form.bgmFile.name}</div>}
      <button className="primary-button" disabled={disabled} type="submit">{disabled ? <><LoaderCircle className="spin" size={18} /> Creating clips...</> : <><Play size={18} fill="currentColor" /> Create clips</>}</button>
      {error && <div className="error" role="alert">{error}</div>}
    </form>
  );
}

function MusicIcon() {
  return <span aria-hidden="true">♫</span>;
}

function NumberField({ label, suffix, value, onChange }) {
  return <label>{label}<div className="number-input"><input type="number" min="1" value={value} onChange={(event) => onChange(Number(event.target.value))} />{suffix && <small>{suffix}</small>}</div></label>;
}

function SelectField({ label, value, onChange, options }) {
  return <label>{label}<select value={value} onChange={(event) => onChange(event.target.value)}>{options.map((option) => <option key={option}>{option}</option>)}</select></label>;
}
