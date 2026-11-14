import { API_BASE_URL } from "../config";

async function request(path, options) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, options);
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

export function getJob(jobId, signal) {
  return request(`/api/jobs/${encodeURIComponent(jobId)}`, { signal });
}
