const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

// Execute the shipped bundle without connecting to the real Anna host.
const source = fs.readFileSync(path.join(__dirname, "../bundle/app.js"), "utf8")
  .replace(/^import .*;$/m, "")
  .replace(/^boot\(\);$/m, "");

function bundle(lang, response) {
  const context = vm.createContext({ window: {}, localStorage: { getItem: () => lang } });
  vm.runInContext(source, context);
  context.host = { tools: { invoke: async () => response } };
  vm.runInContext("anna = host", context);
  return context;
}

test("deployment failures retain diagnostics and provide guidance in both languages", async () => {
  for (const [lang, hint] of [["zh", "检查所选 Agent"], ["en", "check that this Agent"]]) {
    for (const response of [
      { ok: false, error: { code: "executa_not_deployed", message: "Deployment unavailable" } },
      { success: false, error: "init failed: executa 'tool-test' is not deployed on the selected agent" },
    ]) {
      const context = bundle(lang, response);
      await assert.rejects(vm.runInContext("invokeWorld({ action: 'init' })", context), error => {
        context.failure = error;
        const message = vm.runInContext("friendlyError(failure)", context);
        assert.ok(message.includes(hint));
        assert.ok(message.includes(error.message));
        assert.ok(!message.includes("[object Object]"));
        return true;
      });
    }
  }
});

test("unrelated failures remain visible and successful envelopes still unwrap", async () => {
  const context = bundle("en", { ok: true, result: { value: 42 } });
  assert.equal((await vm.runInContext("invokeWorld({})", context)).value, 42);
  context.failure = new Error("Storage permission denied");
  assert.equal(vm.runInContext("friendlyError(failure)", context), "Storage permission denied");
});
