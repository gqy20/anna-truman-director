// Regression test for bundle/world.js — verifies the Python→JS port stays
// behaviorally correct, WITHOUT a real LLM or storage (decide is driven by a
// fake anna). Zero deps. Run: `node bundle/world.test.mjs`
import assert from "node:assert";
import {
  cafeTown,
  seedOccupants,
  snapshot,
  fromSnapshot,
  advanceTick,
  applyEvent,
  recordEvent,
  applyInjectEvent,
  tick,
  buildFromSpec,
  validateSpec,
} from "./world.js";

let pass = 0;
const ok = (name) => { pass++; console.log("  ✓", name); };

// fake anna: llm.complete returns a canned decision; storage.set records calls.
function fakeAnna(text) {
  const sets = [];
  return {
    sets,
    llm: { complete: async () => ({ content: { type: "text", text } }) },
    storage: { set: async ({ value }) => { sets.push(value); return {}; } },
  };
}
const fresh = () => { const w = cafeTown(); seedOccupants(w); return w; };

console.log("cafeTown + seedOccupants");
{
  const w = cafeTown();
  seedOccupants(w);
  assert.equal(Object.keys(w.agents).length, 3);
  assert.equal(Object.keys(w.locations).length, 6);
  assert.ok(w.locations.loc_alice_home.occupants.has("alice"));
  assert.equal(w.current_tick, 0);
  assert.equal(w.world_time, "08:00");
  ok("3 agents, 6 locations, alice seeded at home, tick 0 / 08:00");
}

console.log("advanceTick — 5min step + midnight wrap");
{
  const w = cafeTown();
  w.world_time = "23:55";
  advanceTick(w);
  assert.equal(w.world_time, "00:00", "wraps at midnight");
  assert.equal(w.current_tick, 1);
  w.world_time = "08:00";
  advanceTick(w);
  assert.equal(w.world_time, "08:05");
  ok("23:55→00:00 wrap; 08:00→08:05 step");
}

console.log("applyEvent — move is bidirectional on occupants");
{
  const w = fresh();
  applyEvent(w, { agent_id: "alice", action: "move", target: "loc_cafe", reason: "开门营业" });
  assert.ok(!w.locations.loc_alice_home.occupants.has("alice"), "removed from old");
  assert.ok(w.locations.loc_cafe.occupants.has("alice"), "added to new");
  assert.equal(w.agents.alice.current_location_id, "loc_cafe");
  ok("alice home→cafe: old discarded, new added, current_location_id updated");
}

console.log("applyEvent — talk is bidirectional on familiarity (+0.05, cap 1.0)");
{
  const w = cafeTown();
  applyEvent(w, { agent_id: "alice", action: "talk", target: "bob", reason: "闲聊" });
  assert.equal(w.agents.alice.relationships.bob.familiarity, 0.05);
  assert.equal(w.agents.bob.relationships.alice.familiarity, 0.05, "bidirectional");
  for (let i = 0; i < 30; i++) applyEvent(w, { agent_id: "alice", action: "talk", target: "bob", reason: "" });
  assert.equal(w.agents.alice.relationships.bob.familiarity, 1.0, "caps at 1.0");
  ok("alice↔bob familiarity 0→0.05 bidirectional, caps at 1.0");
}

console.log("snapshot / fromSnapshot — round-trip symmetry");
{
  const w = fresh();
  applyEvent(w, { agent_id: "alice", action: "move", target: "loc_cafe", reason: "" });
  applyEvent(w, { agent_id: "alice", action: "talk", target: "bob", reason: "" });
  recordEvent(w, { agent_id: "alice", action: "move", target: "loc_cafe", reason: "去 cafe" });
  const snap = snapshot(w);
  assert.deepEqual(snap.locations.loc_cafe.occupants, ["alice"]);
  assert.equal(snap.events.length, 1);
  const w2 = fromSnapshot(snap);
  assert.ok(w2.locations.loc_cafe.occupants.has("alice"), "occupants restored to Set");
  assert.equal(w2.locations.loc_alice_home.occupants.has("alice"), false);
  assert.equal(w2.agents.alice.relationships.bob.familiarity, 0.05, "relationships restored");
  assert.equal(w2.events.length, 1, "events restored (bundle restores, unlike Python)");
  ok("snapshot→fromSnapshot preserves occupants(Set)/relationships/events");
}

console.log("snapshot — events truncated to last 20");
{
  const w = cafeTown();
  for (let i = 0; i < 25; i++) recordEvent(w, { agent_id: "alice", action: "rest", reason: `r${i}` });
  assert.equal(w.events.length, 25, "in-memory NOT truncated");
  assert.equal(snapshot(w).events.length, 20, "snapshot takes last 20");
  ok("in-memory keeps 25, snapshot emits last 20");
}

console.log("applyInjectEvent — effective_tick = current+1");
{
  const w = cafeTown();
  w.current_tick = 5;
  const ack = applyInjectEvent(w, { reason: "暴雨来了" });
  assert.equal(ack.effective_tick, 6);
  assert.equal(w._pending_injections.length, 1);
  assert.equal(w._pending_injections[0].effective_tick, 6);
  ok("injection queued at tick 6 (current 5 +1)");
}

console.log("tick — injection drained BEFORE decide, then decide applied + persisted");
{
  const w = fresh();
  applyInjectEvent(w, { reason: "停电了" }); // queued: effective_tick = 0+1 = 1
  const anna = fakeAnna(JSON.stringify({
    events: [{ agent_id: "alice", action: "move", target: "loc_cafe", reason: "出去看看" }],
  }));
  const results = await tick(anna, w, 1);
  assert.equal(w.current_tick, 1);
  assert.equal(w.events[0].event_type, "world_change", "injection folded first");
  assert.equal(w.events[0].description, "停电了");
  assert.equal(w.events[1].actor_agent_id, "alice", "then model move");
  assert.equal(anna.sets.length, 1, "persisted once");
  assert.ok(anna.sets[0].events.some((e) => e.description === "停电了"), "injection in snapshot");
  ok("tick: inject drained first → move applied → storage.set once");
}

console.log("decide / parseEvents — tolerates fence, bare array, dict, prose; garbage throws");
{
  const cases = [
    { text: "```json\n{\"events\":[{\"agent_id\":\"alice\",\"action\":\"rest\",\"target\":null,\"reason\":\"歇会儿\"}]}\n```", desc: "fenced" },
    { text: "{\"events\":[]}", desc: "dict empty" },
    { text: "[{\"agent_id\":\"alice\",\"action\":\"rest\",\"target\":null,\"reason\":\"x\"}]", desc: "bare array" },
    { text: "sure! {\"events\":[{\"agent_id\":\"alice\",\"action\":\"rest\",\"target\":null,\"reason\":\"y\"}]} done", desc: "prose-surrounded" },
  ];
  for (const c of cases) {
    const a = fakeAnna(c.text);
    await tick(a, fresh(), 1); // throws if parse fails
  }
  const aBad = fakeAnna("I refuse, here is some prose with no JSON at all.");
  let threw = false;
  try { await tick(aBad, fresh(), 1); } catch { threw = true; }
  assert.ok(threw, "non-JSON response throws (red line 4)");
  ok("parseEvents: fence/bare-array/prose tolerated; garbage throws");
}

console.log("validateSpec — accepts valid, rejects malformed");
{
  const good = {
    name: "tiny",
    world_time: "09:30",
    locations: [{ id: "l1", name: "Home", type: "home", x: 10, y: 10, capacity: 2 }],
    agents: [{ id: "a1", name: "A", occupation: "x", home_location_id: "l1", personality: { openness: 0.5 } }],
  };
  validateSpec(good);
  buildFromSpec(good);
  ok("valid spec accepted + built");

  const expectThrows = (spec, label) => {
    let threw = false;
    try { validateSpec(spec); } catch { threw = true; }
    assert.ok(threw, label);
  };
  expectThrows({ ...good, locations: [] }, "empty locations");
  expectThrows({ ...good, world_time: "25:00" }, "bad HH:MM");
  expectThrows({ ...good, locations: [{ id: "l1", name: "Home", type: "home", x: 200, y: 10, capacity: 2 }] }, "x out of 0-100");
  expectThrows({ ...good, locations: [{ id: "l1", name: "Home", type: "planet", x: 10, y: 10, capacity: 2 }] }, "bad location type");
  expectThrows({ ...good, agents: [{ id: "a1", name: "A", occupation: "x", home_location_id: "l1", personality: { openness: 5 } }] }, "personality out of 0-1");
  expectThrows({ ...good, agents: [{ id: "a1", name: "A", occupation: "x", home_location_id: "nope" }] }, "home_location_id not in locations");
  expectThrows({ ...good, locations: [
    { id: "l1", name: "Home", type: "home", x: 10, y: 10, capacity: 2 },
    { id: "l1", name: "Dup", type: "home", x: 20, y: 20, capacity: 2 },
  ] }, "duplicate location id");
  ok("malformed specs (7 cases) all rejected loudly");
}

console.log(`\nALL PASS (${pass})`);
