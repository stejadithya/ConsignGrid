/** Minimal typed client for the backend API (same-origin via the /api rewrite; cookie auth). */

export class ApiError extends Error {
  status: number;
  code?: string;
  errors?: { loc: (string | number)[]; msg: string }[];

  constructor(status: number, message: string, code?: string, errors?: ApiError["errors"]) {
    super(message);
    this.status = status;
    this.code = code;
    this.errors = errors;
  }
}

type Query = Record<string, string | number | boolean | null | undefined | (string | number)[]>;

export function withQuery(path: string, query?: Query): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((item) => params.append(k, String(item)));
    else params.set(k, String(v));
  }
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

async function request<T>(method: string, path: string, body?: unknown, query?: Query): Promise<T> {
  const res = await fetch(withQuery(`/api${path}`, query), {
    method,
    credentials: "same-origin",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    let message = data?.detail ?? `Request failed (${res.status})`;
    if (data?.errors?.length) {
      message += ": " + data.errors.map((e: { loc: string[]; msg: string }) =>
        `${e.loc.filter((l) => l !== "body").join(".")} ${e.msg}`).join("; ");
    }
    if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth/")) {
      // Full reload on purpose: discards all in-memory state after sign-out / session expiry.
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.href = "/login";
    }
    throw new ApiError(res.status, message, data?.code, data?.errors);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, query?: Query) => request<T>("GET", path, undefined, query),
  post: <T>(path: string, body: unknown = {}) => request<T>("POST", path, body),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  /** DELETE; resolves to true (most deletes answer 204 with no body). */
  del: (path: string) => request<undefined>("DELETE", path).then(() => true),
};
