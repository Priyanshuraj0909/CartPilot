import { useEffect, useRef, useState } from "react";
export function useTask<T>(key: string | number) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const active = useRef<AbortController>();
  useEffect(() => { setData(null); setError(""); setLoading(false); return () => active.current?.abort(); }, [key]);
  async function run(task: (signal: AbortSignal) => Promise<T>, success?: (result: T) => void) {
    active.current?.abort();
    const controller = new AbortController(); active.current = controller;
    setLoading(true); setError(""); setData(null);
    try { const result = await task(controller.signal); if (!controller.signal.aborted) { setData(result); success?.(result); } }
    catch (error) { if (!controller.signal.aborted) setError(error instanceof Error ? error.message : "Analysis failed. Please try again."); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  }
  return { data, loading, error, run };
}
