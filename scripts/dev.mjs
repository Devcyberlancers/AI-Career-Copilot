import { existsSync } from "node:fs";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const backendDir = path.join(rootDir, "backend");
const frontendDir = path.join(rootDir, "frontend");
const defaultPython = path.join(
  backendDir,
  ".venv",
  "Scripts",
  process.platform === "win32" ? "python.exe" : "python",
);
const python = process.env.BACKEND_PYTHON || defaultPython;
const nextCli = path.join(frontendDir, "node_modules", "next", "dist", "bin", "next");

function fail(message) {
  console.error(`\n[dev] ${message}\n`);
  process.exit(1);
}

if (!existsSync(python)) {
  fail(
    `Backend Python was not found at ${python}.\n` +
      "Create backend/.venv first, or set BACKEND_PYTHON to a valid Python executable.",
  );
}

const pythonCheck = spawnSync(python, ["--version"], {
  cwd: backendDir,
  encoding: "utf8",
});

if (pythonCheck.status !== 0) {
  fail(
    "backend/.venv is not usable. This commonly happens after copying or moving a Python virtual environment.\n" +
      "Delete and recreate backend/.venv, then install backend/requirements.txt.",
  );
}

const backendImportCheck = spawnSync(
  python,
  ["-c", "import app.main; print('Backend import check passed')"],
  {
    cwd: backendDir,
    encoding: "utf8",
    env: process.env,
  },
);

if (backendImportCheck.status !== 0) {
  const output = `${backendImportCheck.stdout || ""}\n${backendImportCheck.stderr || ""}`.trim();
  const usefulLines = output.split(/\r?\n/).slice(-18).join("\n");
  fail(
    "Backend import check failed, so neither service was started.\n\n" +
      `${usefulLines}\n\n` +
      "Repair backend/.venv and run `npm run dev` again.",
  );
}

if (!existsSync(nextCli)) {
  fail("Frontend dependencies are missing. Run `npm install` inside the frontend directory.");
}

console.log("[dev] Starting AI Career Copilot");
console.log("[dev] Frontend: http://localhost:3000");
console.log("[dev] Backend:  http://127.0.0.1:8001");
console.log("[dev] Press Ctrl+C to stop both services.\n");

const children = [];
let stopping = false;

function stopProcessTree(child) {
  if (!child.pid || child.exitCode !== null) {
    return;
  }

  if (process.platform === "win32") {
    spawnSync("taskkill", ["/pid", String(child.pid), "/t", "/f"], {
      stdio: "ignore",
    });
    return;
  }

  child.kill("SIGTERM");
}

let backend;
let frontend;

try {
  backend = spawn(
    python,
    ["dev_server.py"],
    {
      cwd: backendDir,
      stdio: "inherit",
      env: process.env,
    },
  );
  children.push(backend);

  frontend = spawn(process.execPath, [nextCli, "dev", "--turbopack"], {
    cwd: frontendDir,
    stdio: "inherit",
    env: process.env,
  });
  children.push(frontend);
} catch (error) {
  children.forEach(stopProcessTree);
  fail(`Unable to start development services: ${error.message}`);
}

function shutdown(exitCode = 0) {
  if (stopping) {
    return;
  }

  stopping = true;
  console.log("\n[dev] Stopping frontend and backend...");
  children.forEach(stopProcessTree);
  process.exit(exitCode);
}

backend.on("error", (error) => {
  console.error(`[backend] Failed to start: ${error.message}`);
  shutdown(1);
});

frontend.on("error", (error) => {
  console.error(`[frontend] Failed to start: ${error.message}`);
  shutdown(1);
});

backend.on("exit", (code) => {
  if (!stopping) {
    console.error(`[backend] Exited with code ${code ?? 1}.`);
    shutdown(code ?? 1);
  }
});

frontend.on("exit", (code) => {
  if (!stopping) {
    console.error(`[frontend] Exited with code ${code ?? 1}.`);
    shutdown(code ?? 1);
  }
});

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));
