import { useCallback, useEffect, useRef, useState } from "react";
import { createJob, getJob, uploadSource } from "../api/jobs";

const POLL_INTERVAL_MS = 2000;

export function useClipJob() {
  const [job, setJob] = useState(null);
  const [error, setError] = useState("");
  const [isStarting, setIsStarting] = useState(false);
  const timer = useRef(null);
  const controller = useRef(null);

  const stop = useCallback(() => {
    clearTimeout(timer.current);
    controller.current?.abort();
    controller.current = null;
  }, []);

  useEffect(() => stop, [stop]);

  const poll = useCallback(async (jobId) => {
    const requestController = new AbortController();
    controller.current = requestController;
    try {
      const nextJob = await getJob(jobId, requestController.signal);
      setJob(nextJob);
      if (nextJob.status === "running") {
        timer.current = setTimeout(() => poll(jobId), POLL_INTERVAL_MS);
      } else {
        controller.current = null;
        setIsStarting(false);
      }
    } catch (requestError) {
      if (requestError.name !== "AbortError") {
        setError(requestError.message);
        setIsStarting(false);
      }
    }
  }, []);

  const start = useCallback(async (payload) => {
    stop();
    setError("");
    setJob(null);
    setIsStarting(true);
    const requestController = new AbortController();
    controller.current = requestController;
    try {
      const source = payload.file
        ? (await uploadSource(payload.file, requestController.signal)).source
        : payload.source;
      const jobPayload = { ...payload, source };
      delete jobPayload.file;
      const { id } = await createJob(jobPayload, requestController.signal);
      await poll(id);
    } catch (requestError) {
      if (requestError.name !== "AbortError") setError(requestError.message);
      setIsStarting(false);
    }
  }, [poll, stop]);

  return { job, error, isStarting, start };
}
