import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

// The Python Executa configures its own stdio streams, but anna-app dev starts
// a Python bridge before the plugin exists. On zh-CN Windows that bridge would
// otherwise inherit GBK and can crash while forwarding valid Unicode JSON.
const env = {
  ...process.env,
  PYTHONUTF8: "1",
  PYTHONIOENCODING: "utf-8",
};

// pnpm can preserve the command separator; Commander must receive the flags.
const forwardedArgs = process.argv.slice(2);
if (forwardedArgs[0] === "--") forwardedArgs.shift();
// Always use the project-pinned CLI, also for direct `node scripts/dev.mjs`.
// Passing an argv array directly avoids Windows .cmd shell quoting problems.
const cli = fileURLToPath(import.meta.resolve("@anna-ai/cli"));
const child = spawn(process.execPath, [cli, "dev", "--executa", "dir=.", ...forwardedArgs], {
  env,
  stdio: "inherit",
  windowsHide: true,
});

child.once("error", (error) => {
  console.error(`Failed to start anna-app dev: ${error.message}`);
  process.exitCode = 1;
});

child.once("exit", (code, signal) => {
  if (signal) console.error(`anna-app dev stopped by ${signal}`);
  process.exitCode = code ?? (signal ? 1 : 0);
});
