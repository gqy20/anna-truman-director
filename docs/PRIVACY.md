# Privacy Policy — World Director (Local)

**Last updated:** 2026-08-19

World Director (Local) is an open-source Anna App that simulates a small AI
town in your local Anna Agent environment. This page explains what data
the App accesses and how it is handled.

## 1. Data scope

The App operates entirely inside your local Anna Agent. It does not run a
remote server of its own. The data it touches falls into three categories:

1. **World state** — agents, locations, events, and the day-story history.
   Stored as a single APS KV entry (`truman:run:world`) on the Anna
   platform, scoped to this App and your account.
2. **Director injections** — short text strings you type into the input
   bar at the bottom of the App. Saved as pending injection entries in
   the same KV record and applied to the world state on the next tick.
3. **Your local model key** — if you connect a Bring-Your-Own-Key
   provider on the Anna LLM settings page, the App's `decide` and
   `narrate` calls are routed to that key. The App does not store, log,
   or exfiltrate your key.

## 2. What we do not do

- We do not collect telemetry, analytics, or crash reports.
- We do not share your world state, prompts, or generated stories with
  any third party.
- We do not use your content to train any model.

## 3. Account and platform controls

The KV record lives on the Anna platform and follows Anna's own privacy
controls. You can revoke an App's permissions or delete its KV entry at
any time from the Anna Developer Console. Removing the App clears all
data it created.

## 4. Open-source

The App's engine and bundle are published under the MIT license at
<https://github.com/gqy20/anna-truman-director>. You can inspect every
line of code that touches your data.

## 5. Contact

Questions or concerns: open an issue on the repository, or contact the
developer on Anna (qingyu_ge_5657 / qingyu_ge@foxmail.com).