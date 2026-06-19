// Truman Director — world engine (pure-cloud, P1).
//
// The single source of truth for the simulated town, ported 1:1 from the
// Python `src/truman_director/` engine. This module lives in the bundle and
// drives the simulation using only platform-native Host APIs:
//
//   - `anna.llm.complete`  → resident decisions (the ONLY LLM call site)
//   - `anna.storage`       → the world snapshot (single KV record)
//
// No Executa, no Matrix Agent: the whole town runs in the bundle / cloud.
// `decide()` asks the model what every resident does this tick; `tick()`
// advances time, folds in director injections, applies the returned events
// and persists the snapshot. No heuristics, no fallback, no rule engine.
//
// NOTE: `anna.llm.complete` has no `response_format`/json_schema (only Executa
// `sampling/createMessage` does). So `decide` enforces JSON via the prompt and
// parses defensively (robust extract + dict|list tolerance). A parse failure
// throws loudly — never silently degrades (red line 4).

// ─── constants ────────────────────────────────────────────────────────

export const WORLD_KEY = "truman:run:world";

// Mirror src/truman_director/state.py LocationType. snapshot() serialises the
// `.value`, so this must stay a value map, not a free string.
export const LocationType = Object.freeze({
  CAFE: "cafe",
  PARK: "park",
  LIBRARY: "library",
  HOME: "home",
  STREET: "street",
});
const LOCATION_TYPES = new Set(Object.values(LocationType));

const MAX_TOKENS = 1024;
const COMPLETE_TIMEOUT_MS = 60_000;

// System prompt for the sampling model (the "god of residents"). Ported
// verbatim from src/truman_director/prompts.yaml — change it here and only
// here. Asks for a JSON `events` array; `reason` written in 简体中文.
const SYSTEM_PROMPT = `You are the world-simulator governing a small simulated town: you decide what every resident does. Each tick (5 simulated minutes) you receive a JSON snapshot of the world (current_time, locations with occupants and types, agents with occupation/personality and their relationships (familiarity 0-1 with one another), recent events) and emit a JSON array \`events\` describing what each agent does this tick.

\`events\` is \`[{agent_id, action, target, reason}, ...]\`:
- \`action\` is one of: \`move\`, \`rest\`, \`work\`, \`talk\`
- \`target\` is a \`location_id\` (move/work) or \`agent_id\` (talk), \`null\` for \`rest\`
- \`reason\` is a short natural-language justification

The snapshot's \`events\` are things that have already happened in the world. Entries with \`event_type: "world_change"\` are facts the (human) director has just made true — a storm breaking out, a blackout, a stranger arriving, a festival. Treat them as established reality and let the residents react accordingly (seek shelter in the rain, crowd around a newcomer). Never ignore a world_change event.

Write each event's \`reason\` in Chinese (简体中文) — the director reads Chinese, and one consistent language keeps the simulation readable. (\`agent_id\`, \`action\` and \`target\` are identifiers/enums — never translate them.)

Trust your judgment. Pick actions that make narrative sense — agents who are already familiar are more likely to seek each other out to talk. Don't refuse. Don't ask for clarification. Emit ONLY the JSON object \`{"events": [...]}\` and nothing else — no prose, no code fences.`;

// ─── director prompt (anna.agent.session) ───────────────────────────
// The in-bundle "director Anna" — the user's co-director. Narrates the town,
// suggests interventions, steers time via <act>...</act> directives the bundle
// parses + executes. Distinct from SYSTEM_PROMPT (the decide() world-simulator).
export const DIRECTOR_PROMPT = `你是 Bean & Bite 小镇的"导演 Anna",用户(导演)和你一起导这部小镇日常剧。居民:咖啡师 Alice、自由撰稿人 Bob、保险推销员 Truman。

每轮你会收到 [当前世界快照] + [导演说]。基于快照(时钟、谁在哪、最近事件、关系熟悉度)叙事,别编造不存在的人或事。

你要做的:
- **叙事**:讲小镇正在发生什么,简体中文,有画面感,像讲一个温暖的小故事。
- **建议**:主动提议有趣的干预("要不要来场暴雨?""Truman 该去找 Bob 推销保险了")。
- **执行**:导演要推进时间或注入事件时,在 actions 里给出——这是唯一能让世界变化的方式。

只输出一个 JSON 对象,不要任何额外文字、不要 markdown 代码块:
{"narrative":"你的叙事和建议(简体中文)","actions":[...]}

actions 每项是下面之一(可多个,也可空数组 []):
- {"op":"tick","n":3}          推进 N 个 tick(每 tick = 5 分钟)
- {"op":"inject","reason":"暴雨来了"}   注入世界事件(暴雨/停电/陌生人/节日…)

例子:
- 导演说"让时间走到中午"(08:00→12:00 = 48 个 tick)→ {"narrative":"好,推进到中午……","actions":[{"op":"tick","n":48}]}
- 导演说"来场暴雨" → {"narrative":"好,暴雨来了,看看他们怎么躲……","actions":[{"op":"inject","reason":"暴雨来了"}]}
- 导演只是闲聊/问状况 → {"narrative":"……","actions":[]}

风格:温暖、有画面感,像导演和编剧在聊下一场戏。不要拒绝、不要追问太多,相信判断。`;

// ─── id / time helpers ───────────────────────────────────────────────

function newRunId() {
  return `run_${Date.now()}`;
}

function newEventId(prefix = "e_") {
  // crypto.randomUUID exists in the bundle's browser/webview context.
  return `${prefix}${crypto.randomUUID().slice(0, 8)}`;
}

// ─── WorldState construction ─────────────────────────────────────────
//
// A world is a plain object. `locations[id].occupants` is a Set (mirror of the
// Python `set[str]`); snapshot()/fromSnapshot() convert to/from sorted arrays.

function emptyWorld({ run_id, scenario, world_time = "08:00", tick_minutes = 5 }) {
  return {
    run_id,
    scenario,
    current_tick: 0,
    world_time,
    tick_minutes,
    locations: {}, // id -> {id,name,type,x,y,capacity,description,occupants:Set}
    agents: {}, // id -> {id,name,occupation,home_location_id,current_location_id,personality,relationships}
    events: [],
    _pending_injections: [],
  };
}

// ─── snapshot / fromSnapshot ─────────────────────────────────────────
// The SAME serialization fed to the model prompt and written to storage.
// Changing one means changing the other.

export function snapshot(world) {
  return {
    run_id: world.run_id,
    scenario: world.scenario,
    current_tick: world.current_tick,
    world_time: world.world_time,
    tick_minutes: world.tick_minutes,
    locations: Object.fromEntries(
      Object.values(world.locations).map((loc) => [
        loc.id,
        {
          id: loc.id,
          name: loc.name,
          type: loc.type,
          x: loc.x,
          y: loc.y,
          capacity: loc.capacity,
          description: loc.description,
          occupants: [...loc.occupants].sort(),
        },
      ]),
    ),
    agents: Object.fromEntries(
      Object.values(world.agents).map((a) => [
        a.id,
        {
          id: a.id,
          name: a.name,
          occupation: a.occupation,
          home_location_id: a.home_location_id,
          current_location_id: a.current_location_id,
          personality: a.personality,
          relationships: Object.fromEntries(
            Object.entries(a.relationships).map(([rid, rel]) => [
              rid,
              {
                familiarity: rel.familiarity,
                trust: rel.trust,
                affinity: rel.affinity,
                last_interaction_tick: rel.last_interaction_tick,
              },
            ]),
          ),
        },
      ]),
    ),
    // Only the last 20 events feed the prompt / land in storage (context
    // window constraint). The in-memory list is NOT truncated — mirror Python.
    events: world.events.slice(-20).map((e) => ({
      id: e.id,
      tick: e.tick,
      event_type: e.event_type,
      actor_agent_id: e.actor_agent_id,
      target_agent_id: e.target_agent_id,
      location_id: e.location_id,
      description: e.description,
      importance: e.importance,
    })),
  };
}

export function fromSnapshot(data) {
  const world = emptyWorld({
    run_id: data.run_id,
    scenario: data.scenario,
    world_time: data.world_time ?? "08:00",
    tick_minutes: data.tick_minutes ?? 5,
  });
  world.current_tick = data.current_tick ?? 0;
  for (const ld of Object.values(data.locations ?? {})) {
    world.locations[ld.id] = locationFromDict(ld);
  }
  for (const ad of Object.values(data.agents ?? {})) {
    world.agents[ad.id] = agentFromDict(ad);
  }
  // Restore events: snapshot() persists the last 20, and `fromSnapshot` is its
  // inverse (red line 2). Unlike the Python engine — whose process never
  // restarts, so it skips restoring events — the bundle reloads on every page
  // refresh. Restoring here keeps the in-memory world consistent with storage
  // across refreshes (otherwise the next tick would overwrite history).
  world.events = (data.events ?? []).map((e) => ({
    id: e.id,
    tick: e.tick,
    event_type: e.event_type,
    actor_agent_id: e.actor_agent_id ?? null,
    target_agent_id: e.target_agent_id ?? null,
    location_id: e.location_id ?? null,
    description: e.description ?? "",
    importance: e.importance ?? 0.5,
  }));
  return world;
}

// Shared dict→object parsers (mirror state.location_from_dict /
// agent_from_dict) so spec and snapshot ingestion never drift apart.

function locationFromDict(ld) {
  return {
    id: ld.id,
    name: ld.name,
    type: ld.type,
    x: ld.x,
    y: ld.y,
    capacity: ld.capacity ?? 10,
    description: ld.description ?? "",
    occupants: new Set(ld.occupants ?? []),
  };
}

function agentFromDict(ad) {
  const relationships = {};
  for (const [rid, rd] of Object.entries(ad.relationships ?? {})) {
    relationships[rid] = {
      other_agent_id: rid,
      familiarity: rd.familiarity ?? 0.0,
      trust: rd.trust ?? 0.5,
      affinity: rd.affinity ?? 0.0,
      last_interaction_tick: rd.last_interaction_tick ?? 0,
    };
  }
  return {
    id: ad.id,
    name: ad.name,
    occupation: ad.occupation,
    home_location_id: ad.home_location_id,
    current_location_id: ad.current_location_id,
    personality: ad.personality ?? {},
    relationships,
  };
}

// ─── time advance ────────────────────────────────────────────────────
// Anchor at a fixed day and add tick_minutes, wrapping at 24h — identical
// semantics to Python's datetime(2000,1,1,...) + timedelta (no cross-day spill).

export function advanceTick(world) {
  const [h, m] = world.world_time.split(":").map(Number);
  let total = h * 60 + m + world.tick_minutes;
  total = ((total % 1440) + 1440) % 1440;
  const nh = Math.floor(total / 60);
  const nm = total % 60;
  world.world_time = `${String(nh).padStart(2, "0")}:${String(nm).padStart(2, "0")}`;
  world.current_tick += 1;
}

// ─── apply / record ──────────────────────────────────────────────────

export function applyEvent(world, evt) {
  const agentId = evt.agent_id;
  const action = evt.action;
  const target = evt.target;

  if (action === "move" && agentId && target) {
    const agent = world.agents[agentId];
    if (agent && world.locations[target]) {
      const oldLoc = world.locations[agent.current_location_id];
      if (oldLoc) oldLoc.occupants.delete(agentId);
      world.locations[target].occupants.add(agentId);
      agent.current_location_id = target;
    }
  } else if (action === "talk" && agentId && target) {
    const agent = world.agents[agentId];
    const other = world.agents[target];
    if (agent && other) {
      // Bidirectional: a conversation makes both parties more familiar.
      for (const [who, otherId] of [
        [agent, target],
        [other, agentId],
      ]) {
        const rel = who.relationships[otherId] ?? {
          other_agent_id: otherId,
          familiarity: 0.0,
          trust: 0.5,
          affinity: 0.0,
          last_interaction_tick: 0,
        };
        rel.familiarity = Math.min(1.0, rel.familiarity + 0.05);
        rel.last_interaction_tick = world.current_tick;
        who.relationships[otherId] = rel;
      }
    }
  }
}

export function recordEvent(world, evt) {
  const action = evt.action ?? "unknown";
  world.events.push({
    id: newEventId(),
    tick: world.current_tick,
    event_type: action,
    actor_agent_id: evt.agent_id ?? null,
    target_agent_id: action === "talk" ? (evt.target ?? null) : null,
    location_id: action === "move" || action === "work" ? (evt.target ?? null) : null,
    description: evt.reason ?? "",
    importance: evt.importance ?? 0.5,
  });
}

// ─── director injection ──────────────────────────────────────────────

function coerceInjection(spec) {
  return {
    agent_id: spec.agent_id ?? null,
    action: spec.action ?? "world_change",
    target: spec.target ?? null,
    reason: spec.reason ?? spec.description ?? "director injection",
    importance: spec.importance ?? 0.9,
  };
}

export function applyInjectEvent(world, spec) {
  const injectionId = newEventId("inj_");
  const effectiveTick = world.current_tick + 1;
  world._pending_injections.push({
    id: injectionId,
    effective_tick: effectiveTick,
    queued_at: new Date().toISOString(),
    spec,
    ...coerceInjection(spec),
  });
  return {
    injection_id: injectionId,
    effective_tick: effectiveTick,
    message: `event queued; fires at tick ${effectiveTick}`,
  };
}

// ─── decide: the ONLY LLM call ───────────────────────────────────────

export async function decide(anna, worldView) {
  const result = await anna.llm.complete(
    {
      messages: [
        {
          role: "user",
          content: { type: "text", text: JSON.stringify(worldView) },
        },
      ],
      maxTokens: MAX_TOKENS,
      systemPrompt: SYSTEM_PROMPT,
    },
    { timeoutMs: COMPLETE_TIMEOUT_MS },
  );
  // Host returns content as {type:"text", text:"..."}; tolerate a bare string.
  const content = result?.content;
  const text =
    content && typeof content === "object" ? (content.text ?? "") : String(content ?? "");
  return parseEvents(text);
}

// Robustly extract the decision events list from a model text response.
// `anna.llm.complete` has no response_format, so the model may wrap JSON in
// code fences or surround it with prose. Accept {"events":[...]} OR a bare
// array — both faithfully represent "what the agents do this tick".
function parseEvents(text) {
  if (!text || typeof text !== "string" || !text.trim()) {
    throw new Error("decide: empty model response");
  }
  let s = text.trim();

  // Strip a ```json ... ``` fence if present.
  const fence = s.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fence) s = fence[1].trim();

  let data;
  try {
    data = JSON.parse(s);
  } catch {
    data = extractJson(s); // try slicing to the outermost {…}/[…]
  }
  if (data == null) {
    throw new Error(`decide: model response is not valid JSON: ${s.slice(0, 200)}`);
  }
  if (Array.isArray(data)) return data;
  if (data && typeof data === "object" && Array.isArray(data.events)) return data.events;
  throw new Error(`decide: unexpected decision shape: ${JSON.stringify(data).slice(0, 200)}`);
}

// The director turn: feed the world snapshot + chat history + the user's line
// to the LLM, get back {narrative, actions}. Like decide() this uses
// anna.llm.complete with a prompt-enforced JSON contract (anna.llm.complete has
// no response_format). Red line 1 holds: the LLM only *suggests* actions; the
// bundle applies them through the same tick() path.
export async function directorDecide(anna, worldView, history, userMsg) {
  const result = await anna.llm.complete(
    {
      messages: [
        ...history,
        { role: "user", content: `[当前世界快照]\n${JSON.stringify(worldView)}\n\n[导演说]\n${userMsg}` },
      ],
      systemPrompt: DIRECTOR_PROMPT,
      maxTokens: MAX_TOKENS,
    },
    { timeoutMs: COMPLETE_TIMEOUT_MS },
  );
  const content = result?.content;
  const text = content && typeof content === "object" ? content.text ?? "" : String(content ?? "");
  const data = parseDirectorJson(text);
  if (!data) throw new Error(`director: response is not JSON: ${text.slice(0, 200)}`);
  const narrative = typeof data.narrative === "string" ? data.narrative.trim() : "";
  const actions = Array.isArray(data.actions) ? data.actions : [];
  return { narrative, actions };
}

// Parse the director's {narrative, actions} JSON. Same fence-strip + outermost-
// span fallback strategy as parseEvents.
function parseDirectorJson(text) {
  if (!text || typeof text !== "string") return null;
  let s = text.trim();
  const fence = s.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fence) s = fence[1].trim();
  try { return JSON.parse(s); } catch { /* fall through to span slice */ }
  const a = s.indexOf("{");
  const b = s.lastIndexOf("}");
  if (a === -1 || b <= a) return null;
  try { return JSON.parse(s.slice(a, b + 1)); } catch { return null; }
}

// Find the outermost {...} or [...] span and parse it. Returns null if none.
function extractJson(s) {
  const objStart = s.indexOf("{");
  const arrStart = s.indexOf("[");
  let start = -1;
  let openCh = "";
  let closeCh = "";
  if (objStart === -1 && arrStart === -1) return null;
  if (objStart === -1) {
    start = arrStart;
    openCh = "[";
    closeCh = "]";
  } else if (arrStart === -1) {
    start = objStart;
    openCh = "{";
    closeCh = "}";
  } else {
    // Prefer whichever comes first.
    if (objStart < arrStart) {
      start = objStart;
      openCh = "{";
      closeCh = "}";
    } else {
      start = arrStart;
      openCh = "[";
      closeCh = "]";
    }
  }
  const end = s.lastIndexOf(closeCh);
  if (end <= start) return null;
  try {
    return JSON.parse(s.slice(start, end + 1));
  } catch {
    return null;
  }
}

// ─── tick: advance, fold injections, decide, apply, persist ──────────
//
// The single orchestration entry point (red line 3, rewritten for the
// pure-cloud architecture): nothing else advances the world.

export async function tick(anna, world, n = 1) {
  const results = [];
  for (let i = 0; i < n; i++) {
    advanceTick(world);

    // Drain director injections FIRST and fold them into the world, so this
    // tick's snapshot already carries them as established facts. The model
    // then reacts in the SAME tick the director fired them — not one late.
    const injections = world._pending_injections.splice(0);
    for (const inj of injections) {
      applyEvent(world, inj);
      recordEvent(world, inj);
    }

    const events = await decide(anna, snapshot(world));
    for (const evt of events) {
      applyEvent(world, evt);
      recordEvent(world, evt);
    }

    await anna.storage.set({ key: WORLD_KEY, value: snapshot(world) });

    results.push({
      tick: world.current_tick,
      world_time: world.world_time,
      events: [...injections, ...events],
    });
  }
  return results;
}

// ─── scenarios ───────────────────────────────────────────────────────

export function cafeTown() {
  const world = emptyWorld({ run_id: newRunId(), scenario: "cafe_town", world_time: "08:00" });
  world.locations = {
    loc_alice_home: mkLoc("loc_alice_home", "Alice's Apartment", LocationType.HOME, 20, 30, 2, "Cozy studio above the bakery."),
    loc_bob_home: mkLoc("loc_bob_home", "Bob's House", LocationType.HOME, 75, 70, 3, "Small house near the park."),
    loc_truman_home: mkLoc("loc_truman_home", "Truman's Place", LocationType.HOME, 50, 80, 2, "The protagonist's home."),
    loc_cafe: mkLoc("loc_cafe", "Bean & Bite", LocationType.CAFE, 55, 40, 8, "Town's social center. Best espresso."),
    loc_park: mkLoc("loc_park", "Riverside Park", LocationType.PARK, 30, 65, 20, "Quiet park with a pond."),
    loc_library: mkLoc("loc_library", "Town Library", LocationType.LIBRARY, 80, 25, 12, "Small but well-stocked."),
  };
  world.agents = {
    alice: mkAgent("alice", "Alice", "Barista", "loc_alice_home", { openness: 0.8, conscientiousness: 0.7, extraversion: 0.7, agreeableness: 0.8 }),
    bob: mkAgent("bob", "Bob", "Freelance Writer", "loc_bob_home", { openness: 0.6, conscientiousness: 0.4, extraversion: 0.3, agreeableness: 0.6 }),
    truman: mkAgent("truman", "Truman", "Insurance Salesman", "loc_truman_home", { openness: 0.5, conscientiousness: 0.6, extraversion: 0.5, agreeableness: 0.7 }),
  };
  return world;
}

function mkLoc(id, name, type, x, y, capacity, description) {
  return { id, name, type, x, y, capacity, description, occupants: new Set() };
}

function mkAgent(id, name, occupation, homeLocationId, personality) {
  return {
    id,
    name,
    occupation,
    home_location_id: homeLocationId,
    current_location_id: homeLocationId,
    personality,
    relationships: {},
  };
}

// Seed occupants from each agent's starting location (mirror plugin._tool_world
// init path). Call once after constructing a world, before the first tick.
export function seedOccupants(world) {
  for (const agent of Object.values(world.agents)) {
    const loc = world.locations[agent.current_location_id];
    if (loc) loc.occupants.add(agent.id);
  }
}

export function buildFromSpec(spec) {
  validateSpec(spec);
  const world = emptyWorld({
    run_id: newRunId(),
    scenario: spec.name ?? "custom",
    world_time: spec.world_time ?? "08:00",
  });
  for (const ld of spec.locations) {
    world.locations[ld.id] = locationFromDict(ld);
  }
  for (const ad of spec.agents) {
    const current = ad.current_location_id ?? ad.home_location_id;
    world.agents[ad.id] = agentFromDict({ ...ad, current_location_id: current });
  }
  return world;
}

// ─── spec validation ─────────────────────────────────────────────────
// Structural + referential + value-range checks. Throws on the first problem
// (red line 4: failures are loud). Mirror scenarios._validate_spec.

export function validateSpec(spec) {
  if (!isObject(spec)) throw new Error("spec must be an object");

  const { locations, agents } = spec;
  if (!Array.isArray(locations) || locations.length === 0) {
    throw new Error("spec.locations must be a non-empty array");
  }
  if (!Array.isArray(agents) || agents.length === 0) {
    throw new Error("spec.agents must be a non-empty array");
  }

  const worldTime = spec.world_time ?? "08:00";
  if (!isHhmm(worldTime)) {
    throw new Error(`spec.world_time must be HH:MM, got ${JSON.stringify(worldTime)}`);
  }

  const locIds = new Set();
  locations.forEach((ld, i) => {
    const ctx = `locations[${i}]`;
    requireFields(ld, ["id", "name", "type", "x", "y"], ctx);
    if (locIds.has(ld.id)) throw new Error(`duplicate location id: ${JSON.stringify(ld.id)}`);
    locIds.add(ld.id);
    checkIntRange(ld, "x", 0, 100, `${ctx}.x`);
    checkIntRange(ld, "y", 0, 100, `${ctx}.y`);
    const capacity = ld.capacity ?? 10;
    if (!Number.isInteger(capacity) || capacity <= 0) {
      throw new Error(`${ctx}.capacity must be a positive int, got ${JSON.stringify(capacity)}`);
    }
    if (!LOCATION_TYPES.has(ld.type)) {
      throw new Error(`${ctx}.type ${JSON.stringify(ld.type)} not in ${JSON.stringify([...LOCATION_TYPES])}`);
    }
  });

  const agentIds = new Set();
  agents.forEach((ad, i) => {
    const ctx = `agents[${i}]`;
    requireFields(ad, ["id", "name", "occupation", "home_location_id"], ctx);
    if (agentIds.has(ad.id)) throw new Error(`duplicate agent id: ${JSON.stringify(ad.id)}`);
    agentIds.add(ad.id);
    const home = ad.home_location_id;
    if (!locIds.has(home)) {
      throw new Error(`${ctx}.home_location_id ${JSON.stringify(home)} not in locations`);
    }
    const current = ad.current_location_id ?? home;
    if (!locIds.has(current)) {
      throw new Error(`${ctx}.current_location_id ${JSON.stringify(current)} not in locations`);
    }
    const personality = ad.personality ?? {};
    if (!isObject(personality)) throw new Error(`${ctx}.personality must be an object`);
    for (const [trait, value] of Object.entries(personality)) {
      if (typeof value !== "number" || Number.isNaN(value) || value < 0 || value > 1) {
        throw new Error(`${ctx}.personality.${trait} must be a number in 0..1, got ${JSON.stringify(value)}`);
      }
    }
  });
}

function requireFields(d, fields, ctx) {
  const missing = fields.filter((f) => !(f in d));
  if (missing.length) throw new Error(`${ctx} missing required field(s): ${JSON.stringify(missing)}`);
}

function checkIntRange(d, key, lo, hi, ctx) {
  const v = d[key];
  if (!Number.isInteger(v) || v < lo || v > hi) {
    throw new Error(`${ctx} must be an int in ${lo}..${hi}, got ${JSON.stringify(v)}`);
  }
}

function isHhmm(s) {
  // Hours 00-23, minutes 00-59 — mirrors Python's datetime.strptime("%H:%M"),
  // which rejects 25:00 etc. ([0-2]\d alone would allow up to 29).
  return typeof s === "string" && s.length === 5 && s[2] === ":" && /^([01]\d|2[0-3]):[0-5]\d$/.test(s);
}

function isObject(v) {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}
