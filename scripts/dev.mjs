import { spawn } from "node:child_process";

// The Python Executa configures its own stdio streams, but anna-app dev starts
// a Python bridge before the plugin exists. On zh-CN Windows that bridge would
// otherwise inherit GBK and can crash while forwarding valid Unicode JSON.
const env = {
  ...process.env,
  PYTHONUTF8: "1",
  PYTHONIOENCODING: "utf-8",
};

const cliArgs = ["exec", "anna-app", "dev", "--executa", "dir=.", ...process.argv.slice(2)];
const pnpmCli = process.env.npm_execpath;

const child = pnpmCli
  ? spawn(process.execPath, [pnpmCli, ...cliArgs], {
      env,
      stdio: "inherit",
      windowsHide: true,
    })
  : spawn(process.platform === "win32" ? "pnpm.cmd" : "pnpm", cliArgs, {
      env,
      stdio: "inherit",
      windowsHide: true,
      shell: process.platform === "win32",
    });

child.once("error", (error) => {
  console.error(`Failed to start anna-app dev: ${error.message}`);
  process.exitCode = 1;
});

child.once("exit", (code, signal) => {
  if (signal) console.error(`anna-app dev stopped by ${signal}`);
  process.exitCode = code ?? (signal ? 1 : 0);
});
