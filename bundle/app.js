// Truman Director — bundle (pure-cloud, P1).
//
// The whole simulation lives in `./world.js` (the single source of truth,
// ported from the Python engine). This bundle drives it using only platform-
// native Host APIs: `anna.llm.complete` (resident decisions) and `anna.storage`
// (the world snapshot). No Executa, no Matrix Agent — the town runs entirely
// in the bundle / cloud.
//
// The bundle never thinks for the agents: every tick the model decides. The
// user advances time by pressing a button; Anna (the chat partner) is an
// observer/advisor — she reads the world from storage and can suggest director
// injections, which the user fires from this UI.

import { AnnaAppRuntime } from "/static/anna-apps/_sdk/latest/index.js";
import {
  WORLD_KEY,
  cafeTown,
  seedOccupants,
  snapshot,
  fromSnapshot,
  tick,
  applyInjectEvent,
} from "./world.js";

const SCENARIO = "cafe_town";

const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let anna = null;
let world = null; // in-memory WorldState; rehydrated from storage on boot/refresh

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

  try {
    anna = await AnnaAppRuntime.connect();
    await hydrate();
    if (world) {
      enableTick(true);
      setStatus(`Town reloaded — tick ${world.current_tick}.`, "ok");
    } else {
      setStatus("Connected. Press “Start town”.", "ok");
    }
  } catch (err) {
    setStatus(`Runtime unavailable: ${err.message || err}`, "err");
  }
}

// Rehydrate the in-memory world from storage so a page refresh doesn't reset
// the simulation (red line 2: storage is the single source of truth).
async function hydrate() {
  const r = await anna.storage.get({ key: WORLD_KEY });
  const payload = r?.result ?? r;
  const data = payload?.value ?? null;
  world = data ? fromSnapshot(data) : null;
}

// ─── actions ────────────────────────────────────────────────────────

async function onStart() {
  if (!anna) return setStatus("Not connected.", "err");
  setStatus("Starting town…", "info");
  enableTick(false);
  try {
    world = cafeTown();
    seedOccupants(world);
    await anna.storage.set({ key: WORLD_KEY, value: snapshot(world) });
    await refresh();
    enableTick(true);
    setStatus("Town is live.", "ok");
  } catch (err) {
    setStatus(`init failed: ${err.message || err}`, "err");
  }
}

async function onTick(n) {
  if (!anna || !world) return;
  // Fast-forward as a loop of single-tick advances: one render per tick demos
  // motion better than a fire-and-forget batch, and pacing keeps the UI
  // responsive and eases rate limits.
  setStatus(`Advancing ${n} tick(s)…`, "info");
  enableTick(false);
  try {
    const results = await tick(anna, world, n);
    await refresh();
    const last = results.at(-1);
    setStatus(`Advanced to tick ${last.tick} (${last.world_time}).`, "ok");
  } catch (err) {
    setStatus(`tick failed: ${err.message || err}`, "err");
  } finally {
    enableTick(true);
  }
}

// Director injection: parse the input as a spec (full JSON) or fall back to a
// free-text world_change (a storm breaking out, a stranger arriving). Queued
// to fire at the next tick, BEFORE the model decides that tick — so residents
// react in the same tick the director's hand lands.
async function onInject() {
  if (!anna || !world) return;
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
    const ack = applyInjectEvent(world, spec);
    $("inject-input").value = "";
    setStatus(`🎬 queued: “${spec.reason}” — fires at tick ${ack.effective_tick}.`, "info");
  } catch (err) {
    setStatus(`inject failed: ${err.message || err}`, "err");
  }
}

// ─── render ─────────────────────────────────────────────────────────
// Reads the snapshot straight from storage (the single source of truth) and
// renders motion / conversation / director changes — never thinks for agents.

async function refresh() {
  if (!anna) return;
  const r = await anna.storage.get({ key: WORLD_KEY });
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
  // Tick AND inject both require a live in-memory world.
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
