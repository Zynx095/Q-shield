// The only module that talks to the gateway. Every route the dashboard uses is listed in ROUTES, and the
// dashboard contract test (tests/fullstack/test_dashboard_contract.py) checks each one against the real app.

const enc = encodeURIComponent;

export const ROUTES = {
  health: () => "/api/v1/health",
  system: () => "/api/v1/system",
  me: () => "/api/v1/operators/me",
  operators: () => "/api/v1/operators",
  devices: () => "/api/v1/devices",
  trustAll: () => "/api/v1/trust",
  trustHistory: (d, n = 300) => `/api/v1/trust/${enc(d)}/history?limit=${n}`,
  events: (n = 300) => `/api/v1/events?limit=${n}`,
  access: (d) => `/api/v1/devices/${enc(d)}/access`,
  recovery: (d) => `/api/v1/devices/${enc(d)}/recovery`,
  twin: (d) => `/api/v1/devices/${enc(d)}/twin`,
  telemetry: (d, n = 20) => `/api/v1/devices/${enc(d)}/telemetry?limit=${n}`,
  observations: (n = 200) => `/api/v1/observations?limit=${n}`,
  evidence: (after = 0, n = 200) => `/api/v1/evidence?after_seq=${after}&limit=${n}`,
  evidenceVerify: () => "/api/v1/evidence/verify",
  pqcKey: () => "/api/v1/pqc/gateway-key",
  // operator actions (role `operator` or `admin`; the gateway re-checks every precondition)
  recoveryStart: (d) => `/api/v1/devices/${enc(d)}/recovery/start`,
  recoveryAbort: (d) => `/api/v1/devices/${enc(d)}/recovery/abort`,
  twinExpected: (d) => `/api/v1/devices/${enc(d)}/twin/expected`,
};

export class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
    this.status = status;
    this.detail = detail;
  }
  get kind() {
    if (this.status === 0) return "network";
    if (this.status === 401) return "auth";
    if (this.status === 403) return "forbidden";
    if (this.status === 404) return "missing";
    if (this.status === 409) return "conflict";
    if (this.status === 422) return "invalid";
    if (this.status === 503) return "unavailable";
    return "error";
  }
}

/** Human explanation of a refusal, keeping the gateway's own reason visible. */
export function explain(err) {
  if (!(err instanceof ApiError)) return String(err && err.message ? err.message : err);
  const d = err.detail;
  const reason = typeof d === "string" ? d : Array.isArray(d) ? d.map((x) => x.msg || JSON.stringify(x)).join("; ") : JSON.stringify(d);
  switch (err.kind) {
    case "network": return "The gateway could not be reached.";
    case "auth": return "Your operator token was rejected. It may be revoked or expired.";
    case "forbidden": return "Your operator role does not allow this action.";
    case "missing": return "The gateway does not know this device.";
    default: return reason || `Request failed (HTTP ${err.status}).`;
  }
}

export function createApi(getToken) {
  async function request(method, path, body) {
    let res;
    try {
      res = await fetch(path, {
        method,
        cache: "no-store",
        headers: { Authorization: `Bearer ${getToken()}`, ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
    } catch {
      throw new ApiError(0, "network_error");
    }
    let data = null;
    try { data = await res.json(); } catch { /* empty or non-JSON body */ }
    if (!res.ok) throw new ApiError(res.status, data && data.detail !== undefined ? data.detail : data);
    return data;
  }
  return {
    get: (path) => request("GET", path),
    post: (path, body) => request("POST", path, body),
    put: (path, body) => request("PUT", path, body),
  };
}
