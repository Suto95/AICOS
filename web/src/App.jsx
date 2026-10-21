import React, { useEffect, useMemo, useState } from "react";
import {
  completeGoogleOAuth,
  createTask,
  disconnectAccount,
  fetchAnalyze,
  getAiSettings,
  getAccounts,
  getHealth,
  getSessionMe,
  getInsightsSummary,
  getTasks,
  refreshSessionToken,
  setTaskStatus,
  startGoogleOAuth,
  updateAiSettings,
  updateQueryFilter,
} from "./api";

const BUCKETS = ["DO NOW", "SCHEDULE", "DELEGATE", "REVIEW LATER", "ELIMINATE"];
const DURATION_OPTIONS = ["Last 3 hours", "Last 24 hours", "Last 3 days", "Last 7 days"];
const ANON_STORAGE_KEY = "aicos_anon_tasks_v1";
const ANON_TASK_LIMIT = 5;

function sortByOrder(items) {
  return [...items].sort((a, b) => Number(a.order || 0) - Number(b.order || 0));
}

function loadAnonymousTasks() {
  try {
    const raw = localStorage.getItem(ANON_STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export default function App() {
  const [sessionToken, setSessionToken] = useState(localStorage.getItem("aicos_session_token") || "");
  const [currentUser, setCurrentUser] = useState(null);
  const [health, setHealth] = useState("checking");
  const [tasks, setTasks] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [insights, setInsights] = useState(null);
  const [bucketDrafts, setBucketDrafts] = useState({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [oauthBusy, setOauthBusy] = useState(false);
  const [durationLabel, setDurationLabel] = useState("Last 24 hours");
  const [anonymousTasks, setAnonymousTasks] = useState(loadAnonymousTasks);
  const [showSignupNudge, setShowSignupNudge] = useState(false);
  const [mergeChoiceNeeded, setMergeChoiceNeeded] = useState(false);
  const [mergeBusy, setMergeBusy] = useState(false);
  const [authHoverOpen, setAuthHoverOpen] = useState(false);
  const [aiSettings, setAiSettings] = useState({
    provider: "openrouter",
    primary_model: "openrouter/free",
    fallback_model: "openrouter/free",
    base_url: "",
    use_env_fallback: true,
  });

  const isSignedIn = Boolean(sessionToken);

  const signedOpenTasks = useMemo(
    () => tasks.filter((t) => t.status !== "done" && t.status !== "deleted"),
    [tasks],
  );

  const signedDoneTasks = useMemo(
    () => tasks.filter((t) => t.status === "done"),
    [tasks],
  );

  const anonOpenTasks = useMemo(
    () => sortByOrder(anonymousTasks.filter((t) => t.status !== "done")),
    [anonymousTasks],
  );

  const anonDoneTasks = useMemo(
    () => sortByOrder(anonymousTasks.filter((t) => t.status === "done")),
    [anonymousTasks],
  );

  useEffect(() => {
    if (sessionToken) {
      localStorage.setItem("aicos_session_token", sessionToken);
    } else {
      localStorage.removeItem("aicos_session_token");
    }
  }, [sessionToken]);

  useEffect(() => {
    localStorage.setItem(ANON_STORAGE_KEY, JSON.stringify(anonymousTasks));
  }, [anonymousTasks]);

  useEffect(() => {
    function handleBeforeUnload(event) {
      if (sessionToken || anonymousTasks.length === 0) {
        return;
      }
      event.preventDefault();
      event.returnValue = "Your pre-login tasks will be lost unless you sign up for free.";
    }

    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [sessionToken, anonymousTasks]);

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
        const nextToken = result.session_token || sessionToken;
        if (result.session_token) {
          setSessionToken(result.session_token);
        }
        setCurrentUser({ user_id: result.user_id, email: result.email });
        window.history.replaceState({}, document.title, window.location.pathname);
        await loadAllForSession(nextToken);
        if (anonymousTasks.length > 0) {
          setMergeChoiceNeeded(true);
        }
      } catch (e) {
        setError(String(e.message || e));
      } finally {
        setOauthBusy(false);
      }
    }

    maybeFinishOAuth();
  }, [anonymousTasks, sessionToken]);

  async function loadAllForSession(targetToken = sessionToken) {
    if (!targetToken) {
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
      const settingsResp = await getAiSettings(targetToken).catch(() => null);
      setTasks(taskResp.items || []);
      setAccounts(accountResp.items || []);
      setInsights(insightResp);
      if (settingsResp) {
        setAiSettings(settingsResp);
      }
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
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

  async function addTaskForBucket(bucketName) {
    const text = String(bucketDrafts[bucketName] || "").trim();
    if (!text) {
      return;
    }

    if (!isSignedIn) {
      if (anonymousTasks.length >= ANON_TASK_LIMIT) {
        setShowSignupNudge(true);
        setError("Sign up for free to add more than 5 tasks.");
        return;
      }
      const nextOrder = anonymousTasks.length
        ? Math.max(...anonymousTasks.map((t) => Number(t.order || 0))) + 1
        : 1;
      const localTask = {
        id: `anon-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        task: text,
        bucket: bucketName,
        status: "open",
        order: nextOrder,
      };
      setAnonymousTasks((prev) => [...prev, localTask]);
      setBucketDrafts((prev) => ({ ...prev, [bucketName]: "" }));
      setError("");
      return;
    }

    setError("");
    setBusy(true);
    try {
      await createTask(sessionToken, text, bucketName);
      setBucketDrafts((prev) => ({ ...prev, [bucketName]: "" }));
      await loadAllForSession(sessionToken);
    } catch (e) {
      setError(String(e.message || e));
      setBusy(false);
    }
  }

  async function markDone(taskId) {
    if (!isSignedIn) {
      setAnonymousTasks((prev) =>
        prev.map((t) => (t.id === taskId ? { ...t, status: "done" } : t)),
      );
      return;
    }
    setBusy(true);
    setError("");
    try {
      await setTaskStatus(sessionToken, taskId, "done");
      await loadAllForSession(sessionToken);
    } catch (e) {
      setError(String(e.message || e));
      setBusy(false);
    }
  }

  async function reopenTask(taskId) {
    if (!isSignedIn) {
      setAnonymousTasks((prev) =>
        prev.map((t) => (t.id === taskId ? { ...t, status: "open" } : t)),
      );
      return;
    }
    setBusy(true);
    setError("");
    try {
      await setTaskStatus(sessionToken, taskId, "open");
      await loadAllForSession(sessionToken);
    } catch (e) {
      setError(String(e.message || e));
      setBusy(false);
    }
  }

  function updateAnonymousTask(taskId, patch) {
    setAnonymousTasks((prev) => prev.map((t) => (t.id === taskId ? { ...t, ...patch } : t)));
  }

  function moveAnonymousTaskWithinBucket(taskId, direction) {
    setAnonymousTasks((prev) => {
      const items = sortByOrder(prev);
      const target = items.find((t) => t.id === taskId);
      if (!target) {
        return prev;
      }
      const sameBucket = items.filter((t) => t.status !== "done" && t.bucket === target.bucket);
      const idx = sameBucket.findIndex((t) => t.id === taskId);
      const swapIdx = direction === "up" ? idx - 1 : idx + 1;
      if (idx < 0 || swapIdx < 0 || swapIdx >= sameBucket.length) {
        return prev;
      }
      const other = sameBucket[swapIdx];
      return items.map((item) => {
        if (item.id === target.id) {
          return { ...item, order: other.order };
        }
        if (item.id === other.id) {
          return { ...item, order: target.order };
        }
        return item;
      });
    });
  }

  async function runFetchAnalyze() {
    if (!sessionToken) {
      setError("Sign up for free and connect Google to use fetch + analyze.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const active = (accounts || []).filter((a) => a.status === "active");
      const accountId = active.length ? active[0].id : null;
      await fetchAnalyze(sessionToken, {
        account_id: accountId,
        duration_label: durationLabel,
        persist: true,
      });
      await loadAllForSession(sessionToken);
    } catch (e) {
      setError(String(e.message || e));
      setBusy(false);
    }
  }

  async function saveAiModelSettings() {
    if (!sessionToken) {
      setError("Sign up for free to save AI settings.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const updated = await updateAiSettings(sessionToken, {
        provider: aiSettings.provider,
        primary_model: aiSettings.primary_model,
        fallback_model: aiSettings.fallback_model,
        base_url: aiSettings.base_url || "",
        use_env_fallback: Boolean(aiSettings.use_env_fallback),
      });
      setAiSettings(updated);
      await loadAllForSession(sessionToken);
    } catch (e) {
      setError(String(e.message || e));
      setBusy(false);
    }
  }

  async function saveAccountFilter(accountId, queryFilter) {
    if (!isSignedIn) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      await updateQueryFilter(sessionToken, accountId, queryFilter);
      await loadAllForSession(sessionToken);
    } catch (e) {
      setError(String(e.message || e));
      setBusy(false);
    }
  }

  async function removeAccount(accountId) {
    if (!isSignedIn) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      await disconnectAccount(sessionToken, accountId);
      await loadAllForSession(sessionToken);
    } catch (e) {
      setError(String(e.message || e));
      setBusy(false);
    }
  }

  async function appendAnonymousTasksToAccount() {
    if (!sessionToken || anonymousTasks.length === 0) {
      setMergeChoiceNeeded(false);
      return;
    }
    setMergeBusy(true);
    setError("");
    try {
      for (const task of anonymousTasks) {
        const created = await createTask(sessionToken, task.task, task.bucket || "REVIEW LATER");
        if (task.status === "done" && created?.item?.id !== undefined) {
          await setTaskStatus(sessionToken, created.item.id, "done");
        }
      }
      setAnonymousTasks([]);
      setMergeChoiceNeeded(false);
      await loadAllForSession(sessionToken);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setMergeBusy(false);
    }
  }

  function discardAnonymousTasks() {
    setAnonymousTasks([]);
    setMergeChoiceNeeded(false);
  }

  function signOut() {
    setSessionToken("");
    setCurrentUser(null);
    setTasks([]);
    setAccounts([]);
    setInsights(null);
  }

  const boardTasks = isSignedIn ? signedOpenTasks : anonOpenTasks;
  const doneTasks = isSignedIn ? signedDoneTasks : anonDoneTasks;

  return (
    <div className="app-shell">
      <div className="floating-actions">
        <div className="floating-fetch">
          <button onClick={runFetchAnalyze} disabled={busy || !isSignedIn}>
            {busy ? "Working..." : "Fetch + Analyze"}
          </button>
          <select value={durationLabel} onChange={(e) => setDurationLabel(e.target.value)}>
            {DURATION_OPTIONS.map((opt) => (
              <option key={opt} value={opt}>{opt}</option>
            ))}
          </select>
        </div>

        <div className="floating-auth" onMouseEnter={() => setAuthHoverOpen(true)} onMouseLeave={() => setAuthHoverOpen(false)}>
          <button className="auth-toggle">
            {isSignedIn ? "Account" : "Sign up for free"}
          </button>
          {authHoverOpen ? (
            <div className="auth-popover">
              <strong>{isSignedIn ? (currentUser?.email || "Signed in") : "Start free"}</strong>
              {!isSignedIn ? (
                <>
                  <button onClick={beginGoogleLogin} disabled={oauthBusy}>{oauthBusy ? "Signing in..." : "Continue with Google"}</button>
                  <button disabled title="Coming soon">Continue with Outlook (soon)</button>
                </>
              ) : (
                <button onClick={signOut}>Sign Out</button>
              )}
            </div>
          ) : null}
        </div>
      </div>

      <header className="brand-header">
        <h1>AICOS - your AI Chief Of Staff</h1>
        <div className={`health ${health === "ok" ? "ok" : "warn"}`}>API Health: {health}</div>
      </header>

      {!isSignedIn && anonymousTasks.length > 0 ? (
        <section className="panel warning-banner">
          <strong>Your tasks are temporary until you sign up for free.</strong>
          <div>Leave this page and these tasks can be lost.</div>
          <button onClick={beginGoogleLogin} disabled={oauthBusy}>{oauthBusy ? "Signing in..." : "Sign up for free"}</button>
        </section>
      ) : null}

      {showSignupNudge && !isSignedIn ? (
        <section className="panel warning-banner">
          <strong>You reached the free preview limit.</strong>
          <div>Add up to 5 tasks in preview mode. Sign up for free to continue adding.</div>
          <button onClick={beginGoogleLogin} disabled={oauthBusy}>{oauthBusy ? "Signing in..." : "Sign up for free"}</button>
        </section>
      ) : null}

      {mergeChoiceNeeded && isSignedIn ? (
        <section className="panel merge-panel">
          <h2>Keep your pre-login tasks?</h2>
          <p>You signed in after creating tasks. Choose whether to append them to your account or discard them.</p>
          <div className="merge-actions">
            <button onClick={appendAnonymousTasksToAccount} disabled={mergeBusy}>{mergeBusy ? "Appending..." : "Append to account"}</button>
            <button onClick={discardAnonymousTasks} disabled={mergeBusy}>Discard temporary tasks</button>
          </div>
        </section>
      ) : null}

      {error ? <div className="error">{error}</div> : null}

      <section className="panel">
        <h2>Summary</h2>
        <div className="summary-row">
          <div><span>Active</span><strong>{isSignedIn ? (insights?.active_tasks ?? "-") : anonOpenTasks.length}</strong></div>
          <div><span>Done</span><strong>{isSignedIn ? (insights?.done_tasks ?? "-") : anonDoneTasks.length}</strong></div>
          <div><span>Memory</span><strong>{insights?.memory_entries ?? "-"}</strong></div>
          <div><span>Events</span><strong>{insights?.recent_events ?? "-"}</strong></div>
        </div>
      </section>

      <section className="panel">
        <h2>{isSignedIn ? `Task Board (${boardTasks.length})` : `Sandbox Task Board (${boardTasks.length})`}</h2>
        <div className="bucket-board">
          {BUCKETS.map((bucketName) => {
            const bucketItems = boardTasks.filter((t) => t.bucket === bucketName);
            return (
              <div className="bucket-column" key={bucketName}>
                <h3>{bucketName} ({bucketItems.length})</h3>
                <div className="bucket-add-row">
                  <input
                    placeholder={`Add in ${bucketName}`}
                    value={bucketDrafts[bucketName] || ""}
                    onChange={(e) => setBucketDrafts((prev) => ({ ...prev, [bucketName]: e.target.value }))}
                  />
                  <button onClick={() => addTaskForBucket(bucketName)} disabled={busy}>Add</button>
                </div>

                {bucketItems.map((task, idx) => (
                  <div className="task-card" key={task.id}>
                    {!isSignedIn ? (
                      <input
                        value={task.task}
                        onChange={(e) => updateAnonymousTask(task.id, { task: e.target.value })}
                      />
                    ) : (
                      <strong>{task.task}</strong>
                    )}

                    <div className="task-actions-row">
                      {!isSignedIn ? (
                        <>
                          <select
                            value={task.bucket}
                            onChange={(e) => updateAnonymousTask(task.id, { bucket: e.target.value })}
                          >
                            {BUCKETS.map((b) => (
                              <option key={b} value={b}>{b}</option>
                            ))}
                          </select>
                          <button onClick={() => moveAnonymousTaskWithinBucket(task.id, "up")} disabled={idx === 0}>↑</button>
                          <button onClick={() => moveAnonymousTaskWithinBucket(task.id, "down")} disabled={idx === bucketItems.length - 1}>↓</button>
                        </>
                      ) : (
                        <small>{task.bucket}</small>
                      )}
                      <button onClick={() => markDone(task.id)} disabled={busy}>Done</button>
                    </div>
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      </section>

      <section className="panel">
        <h2>{isSignedIn ? "Done Tasks" : `Done in Sandbox (${doneTasks.length})`}</h2>
        <ul className="list">
          {doneTasks.map((task) => (
            <li key={task.id}>
              <div>
                <strong>{task.task}</strong>
                <small>{task.bucket}</small>
              </div>
              <button onClick={() => reopenTask(task.id)} disabled={busy}>Reopen</button>
            </li>
          ))}
          {doneTasks.length === 0 ? <li className="muted">No done tasks</li> : null}
        </ul>
      </section>

      <section className="panel">
        <h2>AI Model Settings</h2>
        <div className="grid">
          <label>
            Provider
            <select
              value={aiSettings.provider || "openrouter"}
              onChange={(e) => setAiSettings((prev) => ({ ...prev, provider: e.target.value }))}
            >
              <option value="openai">openai</option>
              <option value="openrouter">openrouter</option>
            </select>
          </label>
          <label>
            Primary Model
            <input
              value={aiSettings.primary_model || ""}
              onChange={(e) => setAiSettings((prev) => ({ ...prev, primary_model: e.target.value }))}
            />
          </label>
          <label>
            Fallback Model
            <input
              value={aiSettings.fallback_model || ""}
              onChange={(e) => setAiSettings((prev) => ({ ...prev, fallback_model: e.target.value }))}
            />
          </label>
          <label>
            Base URL
            <input
              value={aiSettings.base_url || ""}
              onChange={(e) => setAiSettings((prev) => ({ ...prev, base_url: e.target.value }))}
            />
          </label>
        </div>
        <button onClick={saveAiModelSettings} disabled={busy || !isSignedIn}>Save AI Settings</button>
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
