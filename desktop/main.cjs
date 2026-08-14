const { app, BrowserWindow, dialog, shell } = require("electron");
const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { resolveModelRuntime } = require("./model-runtime.cjs");

let mainWindow = null;
let backendProcess = null;
let backendLog = null;
let isQuitting = false;

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : null;
      server.close((error) => {
        if (error) reject(error);
        else if (port) resolve(port);
        else reject(new Error("Could not reserve a local port"));
      });
    });
  });
}

function backendLaunch(port) {
  const backendArgs = ["--port", String(port)];
  if (process.env.OPENNOMARK_NO_PRELOAD === "1") {
    backendArgs.push("--no-preload-models");
  }

  if (app.isPackaged) {
    const executable = process.platform === "win32"
      ? "opennomark-backend.exe"
      : "opennomark-backend";
    return {
      command: path.join(
        process.resourcesPath,
        "backend",
        "opennomark-backend",
        executable,
      ),
      args: backendArgs,
      cwd: process.resourcesPath,
    };
  }

  const repoRoot = path.resolve(__dirname, "..");
  const python = process.env.OPENNOMARK_PYTHON || (process.platform === "win32"
    ? path.join(repoRoot, ".venv", "Scripts", "python.exe")
    : path.join(repoRoot, ".venv", "bin", "python"));
  return {
    command: python,
    args: ["-m", "opennomark.desktop", ...backendArgs],
    cwd: repoRoot,
  };
}

function startBackend(port) {
  const userData = app.getPath("userData");
  const logsDir = path.join(userData, "logs");
  const modelRuntime = resolveModelRuntime({
    isPackaged: app.isPackaged,
    resourcesPath: process.resourcesPath,
    userData,
  });
  fs.mkdirSync(logsDir, { recursive: true });
  if (!modelRuntime.bundled) {
    fs.mkdirSync(modelRuntime.modelsDir, { recursive: true });
  }

  backendLog = fs.createWriteStream(path.join(logsDir, "backend.log"), { flags: "a" });
  backendLog.write(`\n[desktop] starting backend at ${new Date().toISOString()}\n`);
  backendLog.write(`[desktop] models=${modelRuntime.bundled ? "bundled-offline" : "user-cache"}\n`);

  const launch = backendLaunch(port);
  backendProcess = spawn(launch.command, launch.args, {
    cwd: launch.cwd,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
    env: {
      ...process.env,
      PYTHONUNBUFFERED: "1",
      OPENNOMARK_DESKTOP: "1",
      OPENNOMARK_DATA_DIR: userData,
      ...modelRuntime.environment,
    },
  });
  backendProcess.stdout.pipe(backendLog, { end: false });
  backendProcess.stderr.pipe(backendLog, { end: false });
  backendProcess.once("error", (error) => backendLog.write(`[desktop] ${error.stack || error}\n`));
  backendProcess.once("exit", (code, signal) => {
    backendLog?.write(`[desktop] backend exited code=${code} signal=${signal}\n`);
    if (!isQuitting && mainWindow) {
      void dialog.showMessageBox(mainWindow, {
        type: "error",
        title: "OpenNoMark backend stopped",
        message: "The local image-processing service stopped unexpectedly.",
        detail: `OpenNoMark saved diagnostic information to ${path.join(logsDir, "backend.log")}.`,
      });
    }
  });
}

function backendHealthy(port) {
  return new Promise((resolve) => {
    const request = http.get(
      {
        hostname: "127.0.0.1",
        port,
        path: "/api/health",
        timeout: 1000,
      },
      (response) => {
        response.resume();
        resolve(response.statusCode === 200);
      },
    );
    request.once("timeout", () => {
      request.destroy();
      resolve(false);
    });
    request.once("error", () => resolve(false));
  });
}

async function waitForBackend(port, timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (backendProcess?.exitCode !== null) {
      throw new Error(`The backend exited before startup completed (code ${backendProcess.exitCode}).`);
    }
    if (await backendHealthy(port)) return;
    await new Promise((resolve) => setTimeout(resolve, 350));
  }
  throw new Error("Timed out waiting for the local backend to start.");
}

function stopBackend() {
  if (backendProcess && backendProcess.exitCode === null) backendProcess.kill();
  backendProcess = null;
  backendLog?.end();
  backendLog = null;
}

async function createWindow() {
  const port = await freePort();
  mainWindow = new BrowserWindow({
    width: 1320,
    height: 860,
    minWidth: 940,
    minHeight: 640,
    show: false,
    backgroundColor: "#f3f1eb",
    title: "OpenNoMark",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  mainWindow.setMenuBarVisibility(false);
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("https://")) void shell.openExternal(url);
    return { action: "deny" };
  });
  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith(`http://127.0.0.1:${port}/`)) {
      event.preventDefault();
      if (url.startsWith("https://")) void shell.openExternal(url);
    }
  });

  await mainWindow.loadFile(path.join(__dirname, "loading.html"));
  mainWindow.show();
  startBackend(port);

  try {
    await waitForBackend(port);
    await mainWindow.loadURL(`http://127.0.0.1:${port}/`);
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    await dialog.showMessageBox(mainWindow, {
      type: "error",
      title: "OpenNoMark could not start",
      message: "The local image-processing service did not start.",
      detail,
    });
  }

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

const hasSingleInstanceLock = app.requestSingleInstanceLock();
if (!hasSingleInstanceLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (!mainWindow) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.show();
    mainWindow.focus();
  });

  app.whenReady().then(createWindow).catch((error) => {
    void dialog.showErrorBox("OpenNoMark could not start", error.stack || String(error));
    app.quit();
  });
}

app.on("before-quit", () => {
  isQuitting = true;
  stopBackend();
});

app.on("window-all-closed", () => app.quit());
