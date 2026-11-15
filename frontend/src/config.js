export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "";

export const MODEL_OPTIONS = ["tiny", "base", "small", "medium", "large-v3"];

export const DEFAULT_FORM = Object.freeze({
  source: "",
  file: null,
  output: "clips_output",
  num: 1,
  minimum: 20,
  maximum: 55,
  model: "base",
  format: "vertical",
  captions: true,
  aspectRatio: "9:16",
  fontStyle: "HORMOZI",
  aiProvider: "gemini",
  device: "auto",
});
