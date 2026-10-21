import React, { useEffect, useMemo, useState } from "react";
import {
  completeGoogleOAuth,
  createTask,
  disconnectAccount,
  getAccounts,
  getHealth,
  getSessionMe,
  getInsightsSummary,
  getTasks,
  refreshSessionToken,
  setTaskStatus,
  startGoogleOAuth,
  updateQueryFilter,
} from "./api";

const BUCKETS = ["DO NOW", "SCHEDULE", "DELEGATE", "REVIEW LATER", "ELIMINATE"];

export default function App() {
  const [sessionToken, setSessionToken] = useState(localStorage.getItem("aicos_session_token") || "");
  const [currentUser, setCurrentUser] = useState(null);
  const [health, setHealth] = useState("checking");
  const [tasks, setTasks] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [insights, setInsights] = useState(null);
  const [taskText, setTaskText] = useState("");
  const [bucket, setBucket] = useState("REVIEW LATER");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [oauthBusy, setOauthBusy] = useState(false);

  const openTasks = useMemo(() => tasks.filter((t) => t.status === "open"), [tasks]);

  useEffect(() => {
    if (sessionToken) {
      localStorage.setItem("aicos_session_token", sessionToken);
    } else {
      localStorage.removeItem("aicos_session_token");
    }
  }, [sessionToken]);

  useEffect(() => {
    getHealth()
      .then((r) => setHealth(r.status || "unknown"))
      .catch(() => setHealth("down"));
  }, []);

  useEffect(() => {
    async function loadSessionProfile() {
      if (!sessionToken) {
        setCurrentUser(null);
        return;
      }
      try {
        const rotated = await refreshSessionToken(sessionToken);
        const nextToken = rotated?.session_token || sessionToken;
        if (nextToken !== sessionToken) {
          setSessionToken(nextToken);
        }
        const profile = await getSessionMe(nextToken);
        setCurrentUser(profile);
      } catch {
        setSessionToken("");
        setCurrentUser(null);
      }
    }
    loadSessionProfile();
  }, [sessionToken]);

  useEffect(() => {
    async function maybeFinishOAuth() {
      const params = new URLSearchParams(window.location.search);
      const code = params.get("code");
      const state = params.get("state");
      if (!code || !state) {
        return;
      }

      setOauthBusy(true);
      setError("");
      try {
        const redirectUri = `${window.location.origin}${window.location.pathname}`;
        const result = await completeGoogleOAuth(code, state, redirectUri);
        if (result.session_token) {
          setSessionToken(result.session_token);
        }
        setCurrentUser({ user_id: result.user_id, email: result.email });
        window.history.replaceState({}, document.title, window.location.pathname);
        await loadAllForSession(result.session_token || sessionToken);
      } catch (e) {
        setError(String(e.message || e));
      } finally {
        setOauthBusy(false);
      }
    }

    maybeFinishOAuth();
  }, []);

  async function loadAllForSession(targetToken = sessionToken) {
    if (!targetToken) {
      setError("Sign in with Google to load tasks.");
      return;
    }
    setError("");
    setBusy(true);
    try {
      const [taskResp, accountResp, insightResp] = await Promise.all([
        getTasks(targetToken),
        getAccounts(targetToken),
        getInsightsSummary(targetToken),
      ]);
      setTasks(taskResp.items || []);
      setAccounts(accountResp.items || []);
      setInsights(insightResp);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  async function loadAll() {
    await loadAllForSession(sessionToken);
  }

  async function beginGoogleLogin() {
    setError("");
    setOauthBusy(true);
    try {
      const redirectUri = `${window.location.origin}${window.location.pathname}`;
      const result = await startGoogleOAuth(redirectUri);
      window.location.assign(result.auth_url);
    } catch (e) {
      setError(String(e.message || e));
      setOauthBusy(false);
    }
  }

  async function addTask(e) {
    e.preventDefault();
    if (!taskText.trim()) {
      return;
    }
    setError("");
    setBusy(true);
    try {
      await createTask(sessionToken, taskText.trim(), bucket);
      setTaskText("");
      await loadAll();
    } catch (e) {
      setError(String(e.message || e));
      setBusy(false);
    }
  }

  async function markDone(taskId) {
    setBusy(true);
    setError("");
    try {
      await setTaskStatus(sessionToken, taskId, "done");
      await loadAll();
    } catch (e) {
      setError(String(e.message || e));
      setBusy(false);
    }
  }

  async function saveAccountFilter(accountId, queryFilter) {
    setBusy(true);
    setError("");
    try {
      await updateQueryFilter(sessionToken, accountId, queryFilter);
      await loadAll();
    } catch (e) {
      setError(String(e.message || e));
      setBusy(false);
    }
  }

  async function removeAccount(accountId) {
    setBusy(true);
    setError("");
    try {
      await disconnectAccount(sessionToken, accountId);
      await loadAll();
    } catch (e) {
      setError(String(e.message || e));
      setBusy(false);
    }
  }

  function signOut() {
    setSessionToken("");
    setCurrentUser(null);
    setTasks([]);
    setAccounts([]);
    setInsights(null);
  }

  const isSignedIn = Boolean(sessionToken);

  return (
    <div className="app-shell">
      <header className="hero">
        <div className="hero-badge">AICOS Migration UI</div>
        <h1>React Control Surface</h1>
        <p>Parallel frontend for tasks, insights, and account controls.</p>
      </header>

      <section className="panel controls">
        <div>
          <strong>{currentUser?.email || "Not signed in"}</strong>
          <div style={{ fontSize: "0.8rem", color: "var(--muted)" }}>
            {currentUser?.user_id ? `User ${currentUser.user_id}` : "Use Google sign-in to continue"}
          </div>
        </div>
        <button onClick={loadAll} disabled={busy || !isSignedIn}>Refresh Data</button>
        <button onClick={beginGoogleLogin} disabled={oauthBusy}>{oauthBusy ? "Signing in..." : "Continue with Google"}</button>
        <button onClick={signOut} disabled={!isSignedIn}>Sign Out</button>
        <div className={`health ${health === "ok" ? "ok" : "warn"}`}>API Health: {health}</div>
      </section>

      {error ? <div className="error">{error}</div> : null}

      <section className="grid">
        <article className="panel">
          <h2>Create Task</h2>
          <form onSubmit={addTask} className="stack">
            <input
              placeholder="Type a task"
              value={taskText}
              onChange={(e) => setTaskText(e.target.value)}
            />
            <select value={bucket} onChange={(e) => setBucket(e.target.value)}>
              {BUCKETS.map((b) => (
                <option key={b} value={b}>{b}</option>
              ))}
            </select>
            <button type="submit" disabled={busy}>Add</button>
          </form>
        </article>

        <article className="panel">
          <h2>Insights</h2>
          <div className="kpi-grid">
            <div><span>Active</span><strong>{insights?.active_tasks ?? "-"}</strong></div>
            <div><span>Done</span><strong>{insights?.done_tasks ?? "-"}</strong></div>
            <div><span>Memory</span><strong>{insights?.memory_entries ?? "-"}</strong></div>
            <div><span>Events</span><strong>{insights?.recent_events ?? "-"}</strong></div>
          </div>
        </article>
      </section>

      <section className="panel">
        <h2>Open Tasks ({openTasks.length})</h2>
        <ul className="list">
          {openTasks.map((task) => (
            <li key={task.id}>
              <div>
                <strong>{task.task}</strong>
                <small>{task.bucket}</small>
              </div>
              <button onClick={() => markDone(task.id)} disabled={busy}>Mark Done</button>
            </li>
          ))}
          {!openTasks.length ? <li className="muted">No open tasks</li> : null}
        </ul>
      </section>

      <section className="panel">
        <h2>Connected Accounts</h2>
        <ul className="list">
          {accounts.map((acct) => (
            <li key={acct.id} className="account-row">
              <div>
                <strong>{acct.account_email}</strong>
                <small>{acct.status} • {acct.health_status || "unknown"}</small>
              </div>
              <div className="account-actions">
                <input
                  defaultValue={acct.query_filter || ""}
                  onBlur={(e) => saveAccountFilter(acct.id, e.target.value)}
                />
                <button onClick={() => removeAccount(acct.id)} disabled={busy}>Disconnect</button>
              </div>
            </li>
          ))}
          {!accounts.length ? <li className="muted">No active accounts</li> : null}
        </ul>
      </section>
    </div>
  );
}
