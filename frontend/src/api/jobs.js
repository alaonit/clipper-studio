import { API_BASE_URL } from "../config";

const BACKEND_STORAGE_KEY = "clipper_backend_url";

export function getBackendUrl() {
  return localStorage.getItem(BACKEND_STORAGE_KEY) || API_BASE_URL;
}

export function setBackendUrl(value) {
  const url = new URL(value.trim());
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) {
    throw new Error("Enter a valid HTTP(S) backend URL.");
  }
  localStorage.setItem(BACKEND_STORAGE_KEY, url.href.replace(/\/+$/, ""));
}

export function clearBackendUrl() {
  localStorage.removeItem(BACKEND_STORAGE_KEY);
}

async function request(path, options) {
  let response;
  try {
    response = await fetch(`${getBackendUrl()}${path}`, {
      ...options,
      headers: {
        "ngrok-skip-browser-warning": "true",
        ...(options?.headers || {}),
      },
    });
  } catch {
    throw new Error("The local clipper service is unavailable. Start web_app.py and try again.");
  }

  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const message = typeof data === "object" ? data.error : data;
    throw new Error(message || `Request failed (${response.status}).`);
  }
  return data;
}

export function createJob(payload, signal) {
  return request("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
}

export function uploadSource(file, signal) {
  const body = new FormData();
  body.append("file", file);
  return request("/api/uploads", { method: "POST", body, signal });
}

export function getJob(jobId, signal) {
  return request(`/api/jobs/${encodeURIComponent(jobId)}`, { signal });
}

export function fetchJobs(signal) {
  return request("/api/jobs", { signal });
}

export function checkBackend(signal) {
  return request("/api/health", { signal });
}

export function fetchSettings(signal) {
  return request("/api/settings", { signal });
}
