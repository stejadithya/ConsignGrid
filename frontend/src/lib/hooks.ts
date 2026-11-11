"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./api";

type Query = Parameters<typeof api.get>[1];

interface State<T> {
  key: string | null;
  data: T | null;
  error: string | null;
}

/** Fetch JSON from the API. Keeps the previous data while reloading; `reload()` re-fetches. */
export function useApi<T>(path: string | null, query?: Query) {
  const [nonce, setNonce] = useState(0);
  const key = path ? `${path}?${JSON.stringify(query ?? {})}#${nonce}` : null;
  const [state, setState] = useState<State<T>>({ key: null, data: null, error: null });

  useEffect(() => {
    if (!path || !key) return;
    let alive = true;
    api.get<T>(path, query)
      .then((data) => alive && setState({ key, data, error: null }))
      .catch((e) => alive && setState((s) => ({ key, data: s.data, error: e instanceof ApiError ? e.message : String(e) })));
    return () => { alive = false; };
    // `key` captures path + query + reload nonce.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const setData = useCallback((data: T) => setState((s) => ({ ...s, data })), []);
  return { data: state.data, error: state.error, loading: key !== null && state.key !== key, reload, setData };
}

/** Wrap a mutating call with busy + error state. Returns the result or undefined on failure. */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(async <R,>(fn: () => Promise<R>): Promise<R | undefined> => {
    setBusy(true);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      return undefined;
    } finally {
      setBusy(false);
    }
  }, []);
  return { busy, error, setError, run };
}
