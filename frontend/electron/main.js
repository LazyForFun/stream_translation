import { app, BrowserWindow, ipcMain } from "electron";
import { spawn, exec } from "child_process";
import path from "path";
import { fileURLToPath } from "url";
import fs from "fs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

let backendProcess = null;
let audioProcess = null;
let mainWindow = null;
let isQuitting = false;
let audioStartTimer = null;

function isDev() {
  return !app.isPackaged;
}

function getBackendPath() {
  return isDev()
    ? path.join(__dirname, "../../backend/dist/app.exe")
    : path.join(process.resourcesPath, "backend", "dist", "app.exe");
}

function getAudioPath() {
  return isDev()
    ? path.join(__dirname, "../../backend/dist/system_audio_ws_client.exe")
    : path.join(process.resourcesPath, "backend", "dist", "system_audio_ws_client.exe");
}

function killProcessTree(child) {
  return new Promise((resolve) => {
    if (!child || !child.pid) {
      resolve();
      return;
    }

    if (process.platform === "win32") {
      exec(`taskkill /pid ${child.pid} /t /f`, (err, stdout, stderr) => {
        if (err) {
          console.error("Failed to kill process tree:", err);
        }
        if (stdout) console.log("[taskkill stdout]", stdout);
        if (stderr) console.error("[taskkill stderr]", stderr);
        resolve();
      });
    } else {
      try {
        child.kill("SIGTERM");
      } catch (err) {
        console.error("Failed to kill process:", err);
      }
      resolve();
    }
  });
}

function attachLogs(child, name) {
  child.on("error", (err) => {
    console.error(`${name} failed to start:`, err);
  });

  child.stdout?.on("data", (data) => {
    console.log(`[${name} stdout]`, data.toString());
  });

  child.stderr?.on("data", (data) => {
    console.error(`[${name} stderr]`, data.toString());
  });

  child.on("close", (code) => {
    console.log(`${name} exited with code:`, code);

    if (name === "backend") backendProcess = null;
    if (name === "audio") audioProcess = null;
  });
}

function startProcess(exePath, name) {
  console.log(`${name} path =`, exePath);
  console.log(`${name} exists =`, fs.existsSync(exePath));

  if (!fs.existsSync(exePath)) {
    console.error(`${name} exe not found:`, exePath);
    return null;
  }

  const child = spawn(exePath, [], {
    cwd: path.dirname(exePath),
    detached: false,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"]
  });

  attachLogs(child, name);
  return child;
}

function startPythonServices() {
  const backendPath = getBackendPath();
  const audioPath = getAudioPath();

  backendProcess = startProcess(backendPath, "backend");

  audioStartTimer = setTimeout(() => {
    audioProcess = startProcess(audioPath, "audio");
  }, 2000);
}

async function cleanupProcesses() {
  if (audioStartTimer) {
    clearTimeout(audioStartTimer);
    audioStartTimer = null;
  }

  await Promise.all([
    killProcessTree(audioProcess),
    killProcessTree(backendProcess)
  ]);

  audioProcess = null;
  backendProcess = null;
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 900,
    alwaysOnTop: true,
    frame: false,
    transparent: true,
    backgroundColor: "#00000000",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  // "screen-saver" level keeps the window above fullscreen/borderless apps too
  mainWindow.setAlwaysOnTop(true, "screen-saver");

  if (isDev()) {
    mainWindow.webContents.openDevTools();
  }

  mainWindow.webContents.on(
    "did-fail-load",
    (_event, errorCode, errorDescription, validatedURL) => {
      console.error("did-fail-load:", {
        errorCode,
        errorDescription,
        validatedURL
      });
    }
  );

  mainWindow.webContents.on("did-finish-load", () => {
    console.log("did-finish-load:", mainWindow.webContents.getURL());
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  if (isDev()) {
    await mainWindow.loadURL("http://127.0.0.1:7513");
  } else {
    const indexPath = path.join(__dirname, "../dist/index.html");
    console.log("Loading file:", indexPath);
    console.log("index exists =", fs.existsSync(indexPath));
    await mainWindow.loadFile(indexPath);
  }
}

ipcMain.on("window:minimize", () => mainWindow?.minimize());
ipcMain.on("window:close", () => mainWindow?.close());

app.whenReady().then(async () => {
  startPythonServices();
  await createWindow();

  app.on("activate", async () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      await createWindow();
    }
  });
});

app.on("before-quit", async (event) => {
  if (isQuitting) return;

  event.preventDefault();
  isQuitting = true;

  await cleanupProcesses();
  app.quit();
});

app.on("window-all-closed", async () => {
  await cleanupProcesses();

  if (process.platform !== "darwin") {
    app.quit();
  }
});