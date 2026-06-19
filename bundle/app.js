// Truman Director — bundle.
//
// Reads the world snapshot straight from Anna Storage (`truman:run:world`)
// and drives the simulation by invoking the truman-director Executa. The
// bundle never thinks for the agents — every tick the host LLM decides.
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

  try {
    anna = await AnnaAppRuntime.connect();
    setStatus("Connected. Press “Start town”.", "ok");
    await refresh();
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
  try {
    await invokeWorld({ action: "init", scenario: SCENARIO });
    await refresh();
    enableTick(true);
    setStatus("Town is live.", "ok");
  } catch (err) {
    setStatus(`init failed: ${err.message || err}`, "err");
  }
}

async function onTick(n) {
  if (!anna) return;
  // Fast-forward as a loop of single-tick invokes: each invoke carries its own
  // per-invoke sampling budget (max_calls), so this stays under it where one big
  // `tick n=N` would blow it and leave a half-applied world. One render per tick
  // also demos better than a fire-and-forget batch.
  setStatus(`Advancing ${n} tick(s)…`, "info");
  enableTick(false);
  try {
    let last = null;
    for (let i = 0; i < n; i++) {
      last = await invokeWorld({ action: "tick", n: 1 });
      await refresh();
      await sleep(280); // pacing — keeps the UI responsive, eases rate limits
    }
    setStatus(`Advanced to tick ${last.results.at(-1).tick}.`, "ok");
  } catch (err) {
    setStatus(`tick failed: ${err.message || err}`, "err");
  } finally {
    enableTick(true);
  }
}

// ─── render ─────────────────────────────────────────────────────────

async function refresh() {
  if (!anna) return;
  const r = await anna.storage.get({ key: WORLD_KEY });
  // Tolerate {exists,value} | {ok,result:{exists,value}} | bare payload.
  const payload = r?.result ?? r;
  const world = payload?.value ?? null;
  if (!world) return;
  $("clock").textContent = world.world_time;
  $("tick-meta").textContent = `tick ${world.current_tick}`;
  renderMap(world);
  renderTimeline(world);
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
      .map((id) => world.agents[id]?.name || id)
      .join(", ");
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
    .map(
      (e) =>
        `<li><span class="ev-tick">t${e.tick}</span>` +
        `<span class="ev-type ev-${e.event_type}">${e.event_type}</span>` +
        `<span class="ev-desc">${escapeHtml(e.description || e.reason || "")}</span></li>`,
    )
    .join("");
}

function enableTick(on) {
  $("btn-tick").disabled = !on;
  $("btn-tick5").disabled = !on;
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
