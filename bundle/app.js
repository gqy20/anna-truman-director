// Truman Director — bundle (local-Executa, focus-flow).
//
// Drives the simulation by invoking the truman-director Executa (the Python
// stdio plugin in src/truman_director/) over anna.tools.invoke. The bundle
// never thinks for the agents — every tick the host LLM decides inside the
// plugin's decide() (with a strict json_schema response_format, which the
// pure-cloud anna.llm.complete path can't do). The bundle only renders — it
// reads the snapshot the plugin writes to `truman:run:world` — and drives time
// forward. Conversation / direction is handled by the platform Anna in the
// MAIN chat window (see manifest system_prompt_addendum), NOT by an in-bundle
// Anna. This needs the local Matrix Agent online (the Executa is its child).
//
// The minted tool_id is resolved at runtime from window.__ANNA_TOOL_IDS__
// (written by `anna-app dev` / `apps publish`). The literal below is a dev
// fallback when no sidecar is present.

import { AnnaAppRuntime } from "/static/anna-apps/_sdk/latest/index.js";

const EXECUTA_HANDLE = "truman-director";
const EXECUTA_TOOL_ID =
  (typeof window !== "undefined" &&
    window.__ANNA_TOOL_IDS__ &&
    window.__ANNA_TOOL_IDS__[EXECUTA_HANDLE]) ||
  "tool-qingyu_ge-anna-truman-director-sxah66uc";

const SCENARIO = "cafe_town";
const WORLD_KEY = "truman:run:world";

const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let anna = null;

// ─── boot ───────────────────────────────────────────────────────────

async function boot() {
  $("btn-init").addEventListener("click", onStart);
  $("btn-tick").addEventListener("click", () => onTick(1));
  $("btn-tick5").addEventListener("click", () => onTick(5));
  $("btn-inject").addEventListener("click", onInject);
  $("inject-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onInject();
    }
  });

  // Resident dossier: occupant chips on the map open the modal (M1.4).
  $("map").addEventListener("click", (e) => {
    const chip = e.target.closest(".occupant");
    if (chip?.dataset.agentId) showAgent(chip.dataset.agentId);
  });
  $("agent-close").addEventListener("click", () => ($("agent-modal").hidden = true));
  $("agent-modal").addEventListener("click", (e) => {
    if (e.target === $("agent-modal")) $("agent-modal").hidden = true;
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") $("agent-modal").hidden = true;
  });

  // Dramatic openings (M1.3): one tap = inject + auto-run 3 ticks.
  $("openings-list").addEventListener("click", (e) => {
    const card = e.target.closest(".opening");
    if (card?.dataset.openingId) pickOpening(card.dataset.openingId);
  });
  $("openings-skip").addEventListener("click", () => ($("openings").hidden = true));

  try {
    anna = await AnnaAppRuntime.connect();
    const live = await refresh();
    if (live) {
      enableTick(true);
      setStatus(`Town reloaded — ${$("tick-meta").textContent}.`, "ok");
    } else {
      setStatus("Connected. 按 “Start town”,或在主聊天窗让 Anna 帮你开个小镇。", "ok");
    }
    // Re-adopt any tick job still running from before a reload (M1.6).
    recoverJobs().catch(() => {});
  } catch (err) {
    setStatus(`Runtime unavailable: ${err.message || err}`, "err");
  }
}

async function invokeWorld(args) {
  const res = await anna.tools.invoke({
    tool_id: EXECUTA_TOOL_ID,
    method: "world",
    args,
  });
  // Tolerate the runtime's return shapes: plugin envelope {success,data},
  // call-API style {ok,result}, or a bare payload. Only treat an explicit
  // falsy success/ok as failure.
  const ok = res?.success ?? res?.ok ?? true;
  const data = res?.data ?? res?.result ?? res;
  if (!ok) {
    throw new Error(res?.error || res?.message || "invoke failed");
  }
  return data;
}

// ─── actions ────────────────────────────────────────────────────────

async function onStart() {
  if (!anna) return setStatus("Not connected.", "err");
  setStatus("Starting town…", "info");
  enableTick(false);
  try {
    await invokeWorld({ action: "init", scenario: SCENARIO });
    await refresh();
    enableTick(true);
    setStatus("Town is live.", "ok");
    // First-minute stakes (M1.3): offer three dramatic openings instead of
    // "watching people drink coffee". Failure to load openings is not fatal.
    showOpenings().catch(() => {});
  } catch (err) {
    setStatus(`init failed: ${err.message || err}`, "err");
  }
}

// ─── dramatic openings (M1.3) ────────────────────────────────────────

async function showOpenings() {
  const out = await invokeWorld({ action: "list_scenarios" });
  const openings = out?.openings || [];
  if (!openings.length) return;
  const list = $("openings-list");
  list.innerHTML = openings
    .map(
      (o) =>
        `<button class="opening" data-opening-id="${escapeHtml(o.id)}">` +
        `<b>${escapeHtml(o.title)}</b><span>${escapeHtml(o.hint)}</span></button>`,
    )
    .join("");
  $("openings").hidden = false;
}

async function pickOpening(openingId) {
  $("openings").hidden = true;
  try {
    const out = await invokeWorld({ action: "list_scenarios" });
    const opening = (out?.openings || []).find((o) => o.id === openingId);
    if (!opening) return;
    setStatus(`🎬 开场:${opening.title} — 正在上演…`, "info");
    enableTick(false);
    await invokeWorld({ action: "inject_event", event: opening.event });
    // Three sequential single-tick invokes (not n=3): each keeps its own
    // sampling budget and its own ≤90s sync ceiling, matching onTick's loop.
    for (let i = 0; i < 3; i++) {
      await invokeWorld({ action: "tick", n: 1 });
      await refresh();
      await sleep(280);
    }
    setStatus(`开场已生效:${opening.title}。故事开始了。`, "ok");
  } catch (err) {
    setStatus(`opening failed: ${err.message || err}`, "err");
  } finally {
    enableTick(true);
  }
}

// ─── ticking: async job channel first, sync loop fallback (M1.6) ────
// Multi-tick runs go through anna.tools.invokeAsyncAwait: one job carries the
// whole run under its own deadline (sync invokes are hard-clamped to 90s), the
// plugin emits executa/progress per tick, and a reload can re-adopt the job
// via listJobs/getJob. Single ticks stay sync (fast, and the fallback path
// keeps working on older hosts without the job channel).

const CLIENT_TAG = "truman-director";

async function onTick(n) {
  if (!anna) return;
  setStatus(`Advancing ${n} tick(s)…`, "info");
  enableTick(false);
  try {
    if (n > 1 && typeof anna.tools?.invokeAsyncAwait === "function") {
      await tickAsync(n);
    } else {
      await tickSync(n);
    }
  } catch (err) {
    if (err?.code === "not_implemented" && n > 1) {
      await tickSync(n); // older host without the job channel
    } else {
      setStatus(`tick failed: ${err.message || err}`, "err");
    }
  } finally {
    enableTick(true);
  }
}

async function tickAsync(n) {
  const res = await anna.tools.invokeAsyncAwait(
    {
      tool_id: EXECUTA_TOOL_ID,
      method: "world",
      args: { action: "tick", n },
      // Budget: generous margin over ticks (each ≤ one sampling call), min 60s
      // (policy floor). Sync 90s ceiling doesn't apply to job deadlines.
      timeoutMs: Math.max(60_000, 15_000 * n),
      clientTag: CLIENT_TAG,
    },
    {
      onProgress: (ev) => {
        const d = ev?.data || {};
        if (d.kind === "day_story") {
          setStatus(`📖 第 ${d.day} 天的故事写好了。`, "info");
        } else if (d.tick != null) {
          setStatus(`推进中 t${d.tick}(day ${d.world_time ?? ""})…`, "info");
        }
        refresh().catch(() => {}); // snapshot already persisted per tick
      },
    },
  );
  await refresh();
  const data = res?.data ?? res;
  const results = data?.results || [];
  const last = results.at(-1);
  setStatus(`Advanced to tick ${last?.tick ?? "?"}.`, "ok");
}

async function tickSync(n) {
  // Legacy path: loop of single-tick invokes — each carries its own sampling
  // budget and stays under the 90s sync ceiling.
  let last = null;
  for (let i = 0; i < n; i++) {
    last = await invokeWorld({ action: "tick", n: 1 });
    await refresh();
    await sleep(280); // pacing — keeps the UI responsive, eases rate limits
  }
  setStatus(`Advanced to tick ${last.results.at(-1).tick}.`, "ok");
}

// Reload recovery (M1.6): find OUR in-flight tick jobs and re-adopt them —
// progress continues from lastSeq, terminal state resolves like a fresh run.
async function recoverJobs() {
  if (typeof anna.tools?.listJobs !== "function") return;
  let out;
  try {
    out = await anna.tools.listJobs({ clientTag: CLIENT_TAG, state: ["queued", "running"] });
  } catch (err) {
    if (err?.code === "not_implemented") return;
    throw err;
  }
  for (const job of out.jobs || []) {
    setStatus("发现进行中的推进,正在重新接上…", "info");
    enableTick(false);
    pollJob(job.jobId, 0).finally(() => enableTick(true));
  }
}

async function pollJob(jobId, sinceSeq) {
  let seq = sinceSeq;
  for (;;) {
    const snap = await anna.tools.getJob({ jobId, sinceSeq: seq });
    for (const ev of snap.progress || []) {
      const d = ev?.data || {};
      if (d.tick != null) setStatus(`推进中 t${d.tick}…`, "info");
    }
    if (snap.progress?.length) seq = snap.lastSeq;
    if (["succeeded", "failed", "cancelled", "expired"].includes(snap.state)) {
      await refresh();
      setStatus(
        snap.state === "succeeded" ? "推进完成。" : `job ${snap.state}`,
        snap.state === "succeeded" ? "ok" : "err",
      );
      return;
    }
    await sleep(2000);
  }
}

// Director injection: parse the input as a spec (full JSON) or fall back to a
// free-text world_change (a storm breaking out, a stranger arriving). The
// plugin queues it to fire at the next tick, BEFORE the model decides that
// tick — so residents react in the same tick the director's hand lands.
async function onInject() {
  if (!anna) return;
  const raw = ($("inject-input").value || "").trim();
  if (!raw) return;
  let spec;
  if (raw.startsWith("{") || raw.startsWith("[")) {
    try {
      spec = JSON.parse(raw);
    } catch {
      setStatus("Inject JSON malformed — treating as free text.", "info");
      spec = { reason: raw };
    }
  } else {
    spec = { reason: raw };
  }
  try {
    const ack = await invokeWorld({ action: "inject_event", event: spec });
    $("inject-input").value = "";
    setStatus(
      `🎬 queued: “${spec.reason ?? JSON.stringify(spec)}” — fires at tick ${ack.effective_tick}.`,
      "info",
    );
  } catch (err) {
    setStatus(`inject failed: ${err.message || err}`, "err");
  }
}

// ─── render ─────────────────────────────────────────────────────────
// Reads the snapshot straight from storage (the single source of truth) and
// renders motion / conversation / director changes — never thinks for agents.

async function refresh() {
  if (!anna) return false;
  const r = await anna.storage.get({ key: WORLD_KEY });
  // Tolerate {exists,value} | {ok,result:{exists,value}} | bare payload.
  const payload = r?.result ?? r;
  const world = payload?.value ?? null;
  if (!world) return false;
  $("clock").textContent = world.world_time;
  $("tick-meta").textContent = `tick ${world.current_tick} · day ${world.day || 1}`;
  renderMap(world);
  renderTimeline(world);
  renderStories(world);
  return true;
}

// ─── day stories (M1.5) ──────────────────────────────────────────────
// Stories live in the snapshot the plugin writes — render straight from it.
// The latest day is the emotional headline (story + cliffhanger); older days
// collapse so the panel stays about TODAY.

function renderStories(world) {
  const el = $("stories");
  const stories = world.stories || [];
  if (!stories.length) {
    el.innerHTML = `<p class="stories-empty">第一天的故事,会在小镇跨过午夜时写好。</p>`;
    return;
  }
  const latest = stories[stories.length - 1];
  const older = stories.slice(0, -1);
  el.innerHTML =
    `<article class="story story-latest">` +
    `<div class="story-day">Day ${latest.day}</div>` +
    `<p class="story-text">${escapeHtml(latest.story)}</p>` +
    (latest.cliffhanger ? `<p class="story-cliff">${escapeHtml(latest.cliffhanger)}</p>` : "") +
    `</article>` +
    (older.length
      ? `<details class="story story-old"><summary>前 ${older.length} 天</summary>` +
        older
          .slice()
          .reverse()
          .map(
            (s) =>
              `<article class="story" style="margin-top:8px">` +
              `<div class="story-day">Day ${s.day}</div>` +
              `<p class="story-text">${escapeHtml(s.story)}</p>` +
              (s.cliffhanger ? `<p class="story-cliff">${escapeHtml(s.cliffhanger)}</p>` : "") +
              `</article>`,
          )
          .join("") +
        `</details>`
      : "");
}

// ─── scene derivation (snapshot → recent moves / talks / world_change) ─
// Pure functions: flatten the event list into per-location scene bits so the
// map shows *motion* and *conversation*, not just static occupants. A move
// event carries location_id (its destination); a talk event doesn't, so the
// bubble anchors at the speaker's current_location_id (best effort).

function deriveScene(world) {
  const ev = [...(world.events || [])].reverse(); // newest first
  return {
    moves: ev.filter((e) => e.event_type === "move").slice(0, 4),
    talks: ev.filter((e) => e.event_type === "talk").slice(0, 3),
    worldChange: ev.find((e) => e.event_type === "world_change"),
  };
}

function agentName(world, id) {
  return world.agents?.[id]?.name || id || "?";
}

function renderMap(world) {
  const map = $("map");
  map.innerHTML = "";
  const { moves, talks, worldChange } = deriveScene(world);
  const movesAt = {};
  for (const m of moves) (movesAt[m.location_id] ||= []).push(m);
  const talksAt = {};
  for (const t of talks) {
    const lid = world.agents?.[t.actor_agent_id]?.current_location_id;
    if (lid) (talksAt[lid] ||= []).push(t);
  }

  // A director world_change tints the whole stage so the user feels the
  // director's hand (storm / blackout / festival ...).
  const changeText = worldChange?.description || worldChange?.reason || "";
  map.classList.toggle("stage--world-change", !!worldChange);
  map.dataset.change = changeText;

  for (const loc of Object.values(world.locations)) {
    const node = document.createElement("div");
    node.className = `loc loc-${loc.type}`;
    node.style.left = `${loc.x}%`;
    node.style.top = `${loc.y}%`;
    const occupants = (loc.occupants || [])
      .map((id) => {
        const a = world.agents[id];
        const name = a?.name || id;
        // Surface current_activity (idle/work/rest) — work/rest are now real
        // state, not log-only lines, so the map should show who's on shift.
        const act = a?.current_activity;
        const label = act && act !== "idle" ? `${name} · ${act}` : name;
        // Clickable chip → resident dossier (M1.4)
        return `<span class="occupant" data-agent-id="${escapeHtml(id)}">${escapeHtml(label)}</span>`;
      })
      .join(" ");
    const moveBits = (movesAt[loc.id] || [])
      .map(
        (m) =>
          `<div class="loc-move">→ ${escapeHtml(agentName(world, m.actor_agent_id))}` +
          (m.description ? ` · ${escapeHtml(m.description)}` : "") +
          `</div>`,
      )
      .join("");
    const talkBubbles = (talksAt[loc.id] || [])
      .map(
        (t) =>
          `<div class="loc-bubble"><b>${escapeHtml(agentName(world, t.actor_agent_id))}</b>` +
          (t.description ? `: ${escapeHtml(t.description)}` : "") +
          `</div>`,
      )
      .join("");
    node.innerHTML =
      `<span class="loc-name">${escapeHtml(loc.name)}</span>` +
      `<span class="loc-who">${occupants ? escapeHtml(occupants) : "—"}</span>` +
      moveBits +
      talkBubbles;
    map.appendChild(node);
  }
}

function renderTimeline(world) {
  const tl = $("timeline");
  const events = [...(world.events || [])].reverse().slice(0, 30);
  if (!events.length) {
    tl.innerHTML = `<li class="empty">Nothing has happened yet.</li>`;
    return;
  }
  tl.innerHTML = events
    .map((e) => {
      // 戏点高亮 (§3.6): director injections + high-importance beats — the
      // deterministic signals, before narrate starts marking turns (M2).
      const hot = e.event_type === "world_change" || (e.importance ?? 0) >= 0.8;
      return (
        `<li class="${hot ? "ev-hot" : ""}"><span class="ev-tick">t${e.tick}</span>` +
        `<span class="ev-type ev-${e.event_type}">${e.event_type}</span>` +
        `<span class="ev-desc">${escapeHtml(e.description || e.reason || "")}</span></li>`
      );
    })
    .join("");
}

// ─── resident dossier (M1.4) ─────────────────────────────────────────
// Clicking an occupant chip opens the full dossier from get_agent —
// goal (inner life), relationships with names, recent involvement.

async function showAgent(agentId) {
  const modal = $("agent-modal");
  modal.hidden = false;
  $("agent-name").textContent = "…";
  try {
    const d = await invokeWorld({ action: "get_agent", agent_id: agentId });
    const a = d.agent;
    $("agent-name").textContent = a.name;
    $("agent-meta").textContent =
      `${a.occupation} · ${a.current_activity} · at ${d.location?.name ?? "?"}`;
    $("agent-goal").textContent = a.goal || "";
    $("agent-goal").style.display = a.goal ? "" : "none";
    $("agent-rels").innerHTML = (d.relationships || [])
      .map(
        (r) =>
          `<li><span>${escapeHtml(r.name)}${r.last_interaction_tick ? ` · 上次交谈 t${r.last_interaction_tick}` : ""}</span>` +
          `<span class="rel-familiar">熟识 ${(r.familiarity * 100).toFixed(0)}%</span></li>`,
      )
      .join("");
    $("agent-events").innerHTML = (d.recent_events || [])
      .slice()
      .reverse()
      .map(
        (e) =>
          `<li><span class="ev-tick">t${e.tick}</span>${escapeHtml(e.description || e.event_type)}</li>`,
      )
      .join("");
  } catch (err) {
    $("agent-name").textContent = agentId;
    $("agent-meta").textContent = `get_agent failed: ${err.message || err}`;
  }
}

function enableTick(on) {
  // Tick + inject need a live world.
  $("btn-tick").disabled = !on;
  $("btn-tick5").disabled = !on;
  $("btn-inject").disabled = !on;
}

function setStatus(msg, kind) {
  const el = $("status");
  el.textContent = msg;
  el.className = `status ${kind || ""}`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]),
  );
}

boot();
