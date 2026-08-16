// Truman Director — bundle(导演监视器版)。
//
// 渲染层原则(DESIGN §3.6):地图是舞台(剪影+发光点,文字降到悬浮提示),
// 故事是主角(衬线正文),时间线是字幕流;状态栏是 toast,消息只说一次。
// 决策永远在插件内由宿主 LLM 完成(decide + json_schema strict),bundle
// 只渲染 storage 里的同一份快照并驱动时钟——它不思考。

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

// ─── i18n(zh/en) ──────────────────────────────────────────────────────
// 切换影响:静态文案、人物/地点名(zh 用 name_zh,缺失回退 name)、以及
// LLM 输出语言(init/tick 带上 lang,插件按语言拼 prompt 规则)。历史
// 内容(事件描述/日故事)保持生成时的语言——不做事后机器翻译。
let LANG = localStorage.getItem("truman:lang");
if (LANG !== "zh" && LANG !== "en") LANG = "zh";

const T = {
  zh: {
    brand: "楚门镇",
    title: "楚门镇",
    stories: "今日故事",
    subs: "字幕",
    injectPh: "下一场戏,由你说了算——比如:暴雨将至",
    inject: "🎬 注入",
    tick1: "推进 1 tick",
    tick5: "推进 5 ticks",
    openTown: "开 镇",
    opening: "开镇…",
    opened: "开镇",
    emptySub: "没有剧本——居民的每个动作,都是 AI 此刻的决定",
    day: (n) => `第 ${n} 天`,
    act1: "第一幕",
    quiet: "静场开场",
    openingSoon: "开场…",
    openedScene: "已开场",
    dayStoryNew: "📖 新的一天",
    resume: "接续推进…",
    midnight: "午夜后生成",
    prevDays: (n) => `前 ${n} 天`,
    rels: "关系",
    events: "近事",
    close: "关闭",
    act: { work: "工作中", rest: "休息" },
    errConn: (m) => `连接失败:${m}`,
    errQuota: "平台配额用尽——请到 Anna 客户端处理订阅后重试",
    errTimeout: "调用超时,稍后再试",
    injectOk: (t) => `🎬 t${t} 生效`,
  },
  en: {
    brand: "Truman Town",
    title: "Truman Town",
    stories: "Today's Story",
    subs: "Subtitles",
    injectPh: "Direct the next scene — e.g. a storm is coming",
    inject: "🎬 Inject",
    tick1: "Advance 1 tick",
    tick5: "Advance 5 ticks",
    openTown: "OPEN TOWN",
    opening: "Opening the town…",
    opened: "Town opened",
    emptySub: "No script — every move the residents make is the AI's decision, made this very moment",
    day: (n) => `Day ${n}`,
    act1: "ACT I",
    quiet: "Quiet opening",
    openingSoon: "Setting the scene…",
    openedScene: "The scene is set",
    dayStoryNew: "📖 A new day",
    resume: "Resuming…",
    midnight: "Written at midnight",
    prevDays: (n) => `Previous ${n} days`,
    rels: "Relationships",
    events: "Recent",
    close: "Close",
    act: { work: "working", rest: "resting" },
    errConn: (m) => `Connection failed: ${m}`,
    errQuota: "Platform quota exhausted — please fix your subscription in the Anna client and retry",
    errTimeout: "Call timed out — try again shortly",
    injectOk: (t) => `🎬 effective at t${t}`,
  },
};
const t = () => T[LANG];

// 名字/职业/目标按语言取值(zh 优先 *_zh,en 用 canon,goal 相反:canon 是中文)。
const locName = (l) => (LANG === "zh" && l?.name_zh ? l.name_zh : l?.name || "");
const agentName = (a) => (LANG === "zh" && a?.name_zh ? a.name_zh : a?.name || "");
const agentOcc = (a) => (LANG === "zh" && a?.occupation_zh ? a.occupation_zh : a?.occupation || "");
const agentGoal = (a) => (LANG === "zh" ? a?.goal || "" : a?.goal_en || a?.goal || "");

function applyStaticTexts() {
  const s = t();
  document.documentElement.lang = LANG === "zh" ? "zh-CN" : "en";
  document.title = s.title;
  $("brand").textContent = s.brand;
  $("ph-stories").textContent = s.stories;
  $("ph-subs").textContent = s.subs;
  $("inject-input").placeholder = s.injectPh;
  $("inject-input").setAttribute("aria-label", s.inject);
  $("btn-inject").textContent = s.inject;
  $("btn-tick").title = s.tick1;
  $("btn-tick5").title = s.tick5;
  $("btn-lang").textContent = LANG === "zh" ? "EN" : "中";
  $("act-title").textContent = s.act1;
  $("openings-skip").textContent = s.quiet;
  $("h-rels").textContent = s.rels;
  $("h-events").textContent = s.events;
  $("agent-close").setAttribute("aria-label", s.close);
}

async function toggleLang() {
  LANG = LANG === "zh" ? "en" : "zh";
  localStorage.setItem("truman:lang", LANG);
  applyStaticTexts();
  await refresh().catch(() => {}); // 名字/时间码按新语言重渲染
}

// ─── boot ───────────────────────────────────────────────────────────

async function boot() {
  applyStaticTexts();
  $("btn-tick").addEventListener("click", () => onTick(1));
  $("btn-tick5").addEventListener("click", () => onTick(5));
  $("btn-lang").addEventListener("click", () => toggleLang());
  $("btn-inject").addEventListener("click", onInject);
  $("inject-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onInject();
    }
  });

  // 舞台事件委托:居民点 → 档案;空舞台大按钮 → 开镇。
  $("map").addEventListener("click", (e) => {
    const dot = e.target.closest(".dot");
    if (dot?.dataset.agentId) return showAgent(dot.dataset.agentId);
    if (e.target.closest(".big-start")) return onStart();
  });
  $("agent-close").addEventListener("click", () => ($("agent-modal").hidden = true));
  $("agent-modal").addEventListener("click", (e) => {
    if (e.target === $("agent-modal")) $("agent-modal").hidden = true;
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") $("agent-modal").hidden = true;
  });

  // 第一幕(M1.3):章节卡一键开场。
  $("openings-list").addEventListener("click", (e) => {
    const card = e.target.closest(".chapter");
    if (card?.dataset.openingId) pickOpening(card.dataset.openingId);
  });
  $("openings-skip").addEventListener("click", () => ($("openings").hidden = true));

  try {
    anna = await AnnaAppRuntime.connect();
    const live = await refresh();
    if (live) enableTick(true);
    if (typeof anna.tools?.listJobs === "function") recoverJobs().catch(() => {});
  } catch (err) {
    setStatus(t().errConn(err.message || err), "err", 0);
  }
}

async function invokeWorld(args) {
  const res = await anna.tools.invoke({
    tool_id: EXECUTA_TOOL_ID,
    method: "world",
    args,
  });
  // 容忍三种返回形态:插件信封 {success,data} / call API {ok,result} / 裸载荷。
  const ok = res?.success ?? res?.ok ?? true;
  const data = res?.data ?? res?.result ?? res;
  if (!ok) throw new Error(res?.error || res?.message || "invoke failed");
  return data;
}

// ─── actions ────────────────────────────────────────────────────────

async function onStart() {
  if (!anna) return;
  setStatus(t().opening, "info");
  enableTick(false);
  try {
    await invokeWorld({ action: "init", scenario: SCENARIO, lang: LANG });
    await refresh();
    enableTick(true);
    setStatus(t().opened, "ok");
    showOpenings().catch(() => {});
  } catch (err) {
    setStatus(friendlyError(err), "err", 0);
  }
}

// ─── 第一幕:戏剧开场(M1.3) ─────────────────────────────────────────

const CH_NO = { zh: ["壹", "贰", "叁", "肆"], en: ["I", "II", "III", "IV"] };

async function showOpenings() {
  const out = await invokeWorld({ action: "list_scenarios" });
  const openings = out?.openings || [];
  if (!openings.length) return;
  $("openings-list").innerHTML = openings
    .map(
      (o, i) =>
        `<button class="chapter" data-opening-id="${escapeHtml(o.id)}">` +
        `<span class="ch-no">${(CH_NO[LANG][i] ?? i + 1)}</span>` +
        `<span><span class="ch-title">${escapeHtml(LANG === "zh" ? o.title : (o.title_en || o.title))}</span>` +
        `<span class="ch-hint">${escapeHtml(LANG === "zh" ? o.hint : (o.hint_en || o.hint))}</span></span></button>`,
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
    setStatus(t().openingSoon, "info", 0);
    enableTick(false);
    // 注入文案跟随语言:zh 用 event,en 用 event_en(缺失回退 event)。
    const event = LANG === "zh" ? opening.event : (opening.event_en || opening.event);
    await invokeWorld({ action: "inject_event", event });
    // 顺序 3 个单 tick invoke(非 n=3):各自预算、各自 ≤90s 同步上限。
    for (let i = 0; i < 3; i++) {
      await invokeWorld({ action: "tick", n: 1, lang: LANG });
      await refresh();
      await sleep(280);
    }
    setStatus(t().openedScene, "ok");
  } catch (err) {
    setStatus(friendlyError(err), "err", 0);
  } finally {
    enableTick(true);
  }
}

// ─── ticking:async job 优先,sync 循环兜底(M1.6) ──────────────────────

const CLIENT_TAG = "truman-director";

// job 通道缺失的报错因 runtime 而异:平台是 not_implemented,本地 harness 是
// unknown_method(实测 anna-app dev 0.1.30)——两种都回退 sync 循环。
function isJobChannelMissing(err) {
  return err?.code === "not_implemented" || err?.code === "unknown_method";
}

// 已知平台错误 → 一句人话(其余原样透传,失败要响亮但不刷屏)。
function friendlyError(err) {
  const s = err?.message || String(err);
  if (s.includes("APP_QUOTA_EXCEEDED") || s.includes("Subscription expired"))
    return t().errQuota;
  if (s.includes("timed out")) return t().errTimeout;
  return s;
}

async function onTick(n) {
  if (!anna) return;
  setStatus(`t+${n}…`, "info");
  enableTick(false);
  try {
    if (n > 1 && typeof anna.tools?.invokeAsyncAwait === "function") {
      await tickAsync(n);
    } else {
      await tickSync(n);
    }
  } catch (err) {
    if (n > 1 && isJobChannelMissing(err)) {
      await tickSync(n);
    } else {
      setStatus(friendlyError(err), "err", 0);
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
      args: { action: "tick", n, lang: LANG }, // lang:切换后下一次推进即生效
      timeoutMs: Math.max(60_000, 15_000 * n),
      clientTag: CLIENT_TAG,
    },
    {
      onProgress: (ev) => {
        const d = ev?.data || {};
        if (d.kind === "day_story") setStatus(t().dayStoryNew, "info");
        else if (d.tick != null) setStatus(`t${d.tick}…`, "info");
        refresh().catch(() => {});
      },
    },
  );
  await refresh();
  const results = (res?.data ?? res)?.results || [];
  const last = results.at(-1);
  setStatus(`t${last?.tick ?? "?"} ✓`, "ok");
}

async function tickSync(n) {
  for (let i = 0; i < n; i++) {
    await invokeWorld({ action: "tick", n: 1, lang: LANG });
    await refresh();
    await sleep(280);
  }
}

// 重载恢复(M1.6):重新挂接我们的进行中 job。
async function recoverJobs() {
  let out;
  try {
    out = await anna.tools.listJobs({ clientTag: CLIENT_TAG, state: ["queued", "running"] });
  } catch (err) {
    if (isJobChannelMissing(err)) return;
    throw err;
  }
  for (const job of out.jobs || []) {
    setStatus(t().resume, "info");
    enableTick(false);
    pollJob(job.jobId, 0).finally(() => enableTick(true));
  }
}

async function pollJob(jobId, sinceSeq) {
  let seq = sinceSeq;
  for (;;) {
    const snap = await anna.tools.getJob({ jobId, sinceSeq: seq });
    for (const ev of snap.progress || []) {
      if (ev?.data?.tick != null) setStatus(`t${ev.data.tick}…`, "info");
    }
    if (snap.progress?.length) seq = snap.lastSeq;
    if (["succeeded", "failed", "cancelled", "expired"].includes(snap.state)) {
      await refresh();
      setStatus(snap.state === "succeeded" ? "✓" : snap.state, snap.state === "succeeded" ? "ok" : "err");
      return;
    }
    await sleep(2000);
  }
}

// ─── 导演注入 ───────────────────────────────────────────────────────

async function onInject() {
  if (!anna) return;
  const raw = ($("inject-input").value || "").trim();
  if (!raw) return;
  let spec;
  if (raw.startsWith("{") || raw.startsWith("[")) {
    try {
      spec = JSON.parse(raw);
    } catch {
      spec = { reason: raw };
    }
  } else {
    spec = { reason: raw };
  }
  try {
    const ack = await invokeWorld({ action: "inject_event", event: spec });
    $("inject-input").value = "";
    setStatus(t().injectOk(ack.effective_tick), "info");
  } catch (err) {
    setStatus(friendlyError(err), "err", 0);
  }
}

// ─── render:只读快照,不思考 ─────────────────────────────────────────

// 真机调试钩子:opencli/控制台可直接驱动内部动作,不进 UI。
window.__truman = { invokeWorld, refresh, onStart, showOpenings, toggleLang, get lang() { return LANG; } };

let lastStoryDay = null; // cliffhanger 定格检测
let lastMaxTick = -1; // 字幕"新条目"动画判定

async function refresh() {
  if (!anna) return false;
  const r = await anna.storage.get({ key: WORLD_KEY });
  const payload = r?.result ?? r;
  const world = payload?.value ?? null;
  if (!world) {
    renderStageEmpty();
    return false;
  }
  renderTimecode(world);
  renderStage(world);
  renderStories(world);
  renderSubtitles(world);
  lastMaxTick = world.events?.length ? world.events[world.events.length - 1].tick : -1;
  return true;
}

function renderStageEmpty() {
  $("map").innerHTML =
    `<div class="stage-empty">` +
    `<span class="empty-k">STANDBY</span>` +
    `<button class="big-start">${t().openTown}</button>` +
    `<span class="sub">${t().emptySub}</span>` +
    `</div>`;
}

function renderTimecode(world) {
  const tick = String(world.current_tick ?? 0).padStart(3, "0");
  $("timecode").innerHTML =
    `${t().day(world.day || 1)} <span class="tc-dim">·</span> ${escapeHtml(world.world_time || "--:--")}` +
    ` <span class="tc-dim">·</span> t${tick}<span class="tc-caret"></span>`;
}

// 建筑剪影(内联 SVG,CSP 'self' 安全;色由 currentColor 控制)
const SILS = {
  cafe:
    '<path d="M4 11h24v-4H4zM4 12c0 2 1.6 3.4 3.4 3.4S10.8 14 10.8 12c0 2 1.6 3.4 3.4 3.4s3.4-1.4 3.4-3.4c0 2 1.6 3.4 3.4 3.4s3.4-1.4 3.4-3.4"/>' +
    '<path d="M11 28v-8a5 5 0 0 1 10 0v8h-3v-7h-4v7z"/><path d="M22 21h2.6a2.2 2.2 0 0 1 0 4.4H22"/>',
  park:
    '<path d="M16 3l7 10h-4l7 11H6l7-11H9z"/><path d="M14 26h4v6h-4z"/>',
  library:
    '<path d="M3 12L16 4l13 8zM6 26h4V14H6zm8 0h4V14h-4zm8 0h4V14h-4zM3 28h26v-2H3z"/>',
  home:
    '<path d="M5 30V15L16 6l11 9v15h-8v-8h-6v8z"/>',
  street:
    '<path d="M15 30h2V12h-2z"/><path d="M16 4l5 6H11z"/><circle cx="16" cy="13" r="2.4"/>',
};

const ACT_ZH = { work: "工作中", rest: "休息" };
const ACT_EN = { work: "working", rest: "resting" };

function renderStage(world) {
  const stage = $("map");
  const events = world.events || [];
  const newest = events[events.length - 1];
  const injecting = newest && newest.event_type === "world_change";

  // 近期动态(只取快照尾部,纯派生):谁刚到达、谁在交谈
  const tail = events.slice(-8);
  const arrivals = new Set(
    tail.filter((e) => e.event_type === "move" && e.location_id).map((e) => e.location_id),
  );
  const talking = new Set();
  for (const e of tail) {
    if (e.event_type === "talk") {
      if (e.actor_agent_id) talking.add(e.actor_agent_id);
      if (e.target_agent_id) talking.add(e.target_agent_id);
    }
  }

  const byLoc = {};
  for (const id of Object.keys(world.locations || {})) byLoc[id] = [];
  for (const [id, a] of Object.entries(world.agents || {})) {
    (byLoc[a.current_location_id] ||= []).push(id);
  }

  let html = "";
  const ACT = LANG === "zh" ? ACT_ZH : ACT_EN;
  for (const loc of Object.values(world.locations || {})) {
    const dots = (byLoc[loc.id] || [])
      .map((id) => {
        const a = world.agents[id];
        const cls = talking.has(id) ? "talk" : a?.current_activity || "idle";
        const act = ACT[a?.current_activity];
        const tip = escapeHtml(agentName(a || { name: id }) + (act ? ` · ${act}` : ""));
        return `<button class="dot ${cls}" data-agent-id="${escapeHtml(id)}" data-tip="${tip}"></button>`;
      })
      .join("");
    html +=
      `<div class="bld ${dots ? "lit" : ""} ${arrivals.has(loc.id) ? "arrive" : ""}" ` +
      `style="left:${loc.x}%;top:${loc.y}%">` +
      `<svg class="bld-sil" viewBox="0 0 32 32" fill="currentColor" aria-hidden="true">${
        SILS[loc.type] || SILS.street
      }</svg>` +
      `<div class="dots">${dots}</div>` +
      `<span class="bld-name">${escapeHtml(locName(loc))}</span>` +
      `</div>`;
  }
  if (injecting) {
    // 最新事件仍是注入 → 扫光 + 字幕条;居民反应落下后自然消失。
    stage.classList.add("sweep");
    html += `<div class="lower-third">🎬 ${escapeHtml(newest.description || newest.reason || "")}</div>`;
  } else {
    stage.classList.remove("sweep");
  }
  stage.innerHTML = html;
}

function renderStories(world) {
  const el = $("stories");
  const stories = world.stories || [];
  if (!stories.length) {
    el.innerHTML = `<p class="story-day" style="text-align:center;padding:8px 0">${t().midnight}</p>`;
    return;
  }
  const latest = stories[stories.length - 1];
  const older = stories.slice(0, -1);
  el.innerHTML =
    `<article class="story story-latest">` +
    `<div class="story-day">${t().day(latest.day)}</div>` +
    `<p class="story-text">${escapeHtml(latest.story)}</p>` +
    (latest.cliffhanger ? `<p class="story-cliff">${escapeHtml(latest.cliffhanger)}</p>` : "") +
    `</article>` +
    (older.length
      ? `<details class="story-old"><summary>${t().prevDays(older.length)}</summary>` +
        older
          .slice()
          .reverse()
          .map(
            (s) =>
              `<article class="story">` +
              `<div class="story-day">${t().day(s.day)}</div>` +
              `<p class="story-text">${escapeHtml(s.story)}</p>` +
              (s.cliffhanger ? `<p class="story-cliff">${escapeHtml(s.cliffhanger)}</p>` : "") +
              `</article>`,
          )
          .join("") +
        `</details>`
      : "");

  // cliffhanger 定格:新的一天写完时,整窗片刻凝滞(§3.6 戏点)。
  if (lastStoryDay !== null && latest.day !== lastStoryDay) {
    document.body.classList.add("freeze");
    setTimeout(() => document.body.classList.remove("freeze"), 1400);
  }
  lastStoryDay = latest.day;
}

const SUB_MARK = {
  move: "→", talk: "●", work: "▮", rest: "·",
  world_change: "▲", director_inject: "▲",
};

function renderSubtitles(world) {
  const tl = $("timeline");
  const events = [...(world.events || [])].reverse().slice(0, 40);
  tl.innerHTML = events
    .map((e) => {
      const hot = e.event_type === "world_change" || (e.importance ?? 0) >= 0.8;
      return (
        `<li class="sub ${hot ? "sub-hot" : ""}">` +
        `<span class="t">t${e.tick}</span>` +
        `<span class="mark">${SUB_MARK[e.event_type] ?? "·"}</span>` +
        `<span class="txt">${escapeHtml(e.description || e.reason || "")}</span></li>`
      );
    })
    .join("");
}

// ─── 居民档案(M1.4) ─────────────────────────────────────────────────

async function showAgent(agentId) {
  const modal = $("agent-modal");
  modal.hidden = false;
  $("agent-name").textContent = "…";
  try {
    const d = await invokeWorld({ action: "get_agent", agent_id: agentId });
    const a = d.agent;
    $("agent-name").textContent = agentName(a);
    const loc = d.location ? locName(d.location) : "?";
    $("agent-meta").textContent = `${agentOcc(a)} · ${loc}`;
    $("agent-goal").textContent = agentGoal(a);
    $("agent-goal").style.display = agentGoal(a) ? "" : "none";
    $("agent-rels").innerHTML = (d.relationships || [])
      .map(
        (r) =>
          `<li><span>${escapeHtml(LANG === "zh" && r.name_zh ? r.name_zh : r.name)}</span>` +
          `<span class="bar"><i style="width:${Math.round(r.familiarity * 100)}%"></i></span>` +
          `<span class="t">${Math.round(r.familiarity * 100)}%</span></li>`,
      )
      .join("");
    $("agent-events").innerHTML = (d.recent_events || [])
      .slice()
      .reverse()
      .map((e) => `<li><span class="t">t${e.tick}</span>${escapeHtml(e.description || e.event_type)}</li>`)
      .join("");
  } catch (err) {
    $("agent-name").textContent = agentId;
    $("agent-meta").textContent = err.message || String(err);
  }
}

// ─── 基础设施 ───────────────────────────────────────────────────────

function enableTick(on) {
  $("btn-tick").disabled = !on;
  $("btn-tick5").disabled = !on;
  $("btn-inject").disabled = !on;
}

let toastTimer = null;
// kind: ok | err | info;hold=0 表示不自动消失(进行中/错误态)。
function setStatus(msg, kind = "info", holdMs = 3200) {
  const el = $("status");
  el.textContent = msg;
  el.className = `toast show ${kind}`;
  clearTimeout(toastTimer);
  if (holdMs > 0) toastTimer = setTimeout(() => el.classList.remove("show"), holdMs);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]),
  );
}

boot();
