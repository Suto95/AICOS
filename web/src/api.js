const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

function authHeaders(sessionToken) {
  const headers = {
    "Content-Type": "application/json",
  };
  if (sessionToken) {
    headers.Authorization = `Bearer ${sessionToken}`;
  }
  return headers;
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload?.detail || payload?.error || `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return payload;
}

export function getHealth() {
  return request("/health");
}

export function getTasks(sessionToken) {
  return request("/v1/me/tasks", {
    headers: authHeaders(sessionToken),
  });
}

export function createTask(sessionToken, task, bucket) {
  return request("/v1/me/tasks", {
    method: "POST",
    headers: authHeaders(sessionToken),
    body: JSON.stringify({ task, bucket, source: "manual" }),
  });
}

export function setTaskStatus(sessionToken, taskId, status) {
  return request(`/v1/me/tasks/${taskId}/status`, {
    method: "POST",
    headers: authHeaders(sessionToken),
    body: JSON.stringify({ status }),
  });
}

export function getInsightsSummary(sessionToken) {
  return request("/v1/me/insights/summary", {
    headers: authHeaders(sessionToken),
  });
}

export function getAccounts(sessionToken) {
  return request("/v1/me/accounts", {
    headers: authHeaders(sessionToken),
  });
}

export function updateQueryFilter(sessionToken, accountId, queryFilter) {
  return request(`/v1/me/accounts/${accountId}/query-filter`, {
    method: "PATCH",
    headers: authHeaders(sessionToken),
    body: JSON.stringify({ query_filter: queryFilter }),
  });
}

export function disconnectAccount(sessionToken, accountId) {
  return request(`/v1/me/accounts/${accountId}/disconnect`, {
    method: "POST",
    headers: authHeaders(sessionToken),
  });
}

export function createSession(userId, email = "") {
  return request("/v1/auth/session", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ user_id: Number(userId), email }),
  });
}

export function getSessionMe(sessionToken) {
  return request("/v1/auth/me", {
    headers: authHeaders(sessionToken),
  });
}

export function refreshSessionToken(sessionToken) {
  return request("/v1/auth/refresh", {
    method: "POST",
    headers: authHeaders(sessionToken),
  });
}

export function startGoogleOAuth(redirectUri) {
  return request("/v1/auth/google/start", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ redirect_uri: redirectUri || null }),
  });
}

export function completeGoogleOAuth(code, state, redirectUri) {
  return request("/v1/auth/google/callback", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      code,
      state,
      redirect_uri: redirectUri || null,
    }),
  });
}
