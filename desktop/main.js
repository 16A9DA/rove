const { app, BrowserWindow, Tray, Menu, nativeImage, screen, ipcMain } = require("electron");
const fs = require("fs");
const { spawn } = require("child_process");
const path = require("path");

const DEV_URL = "http://localhost:3000";
const PROD_ENTRY = path.join(__dirname, "..", "frontend", "out", "index.html");
const POPOVER_ENTRY = path.join(__dirname, "..", "frontend", "out", "popover.html");
const QUICK_EVENTS_URL = "http://127.0.0.1:8000/api/quick/events";
const BACKEND_DIR = path.join(__dirname, "..", "backend");
const TOKEN_PATH = path.join(BACKEND_DIR, ".rove_token");
const HEALTH_URL = "http://127.0.0.1:8000/health";
let backend = null;

// Starts the backend from the repo's venv unless one is already answering (e.g. started by hand).
// Only a backend we started is stopped on quit. Output goes to ~/Library/Logs/<app>/backend.log.
async function ensureBackend() {
  try {
    const response = await fetch(HEALTH_URL, { signal: AbortSignal.timeout(1000) });
    if (response.ok) return;
  } catch {
    // not running; start it below
  }
  const python = path.join(BACKEND_DIR, ".venv", "bin", "python");
  if (!fs.existsSync(python)) {
    console.error("Rove backend not started: backend/.venv is missing (see README install steps).");
    return;
  }
  fs.mkdirSync(app.getPath("logs"), { recursive: true });
  const log = fs.openSync(path.join(app.getPath("logs"), "backend.log"), "a");
  backend = spawn(python, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"], {
    cwd: BACKEND_DIR,
    env: { ...process.env, PYTHONPATH: path.join(__dirname, "..") },
    stdio: ["ignore", log, log],
  });
  backend.on("exit", () => {
    backend = null;
  });
}

// Shared secret the backend creates (0600) on first start; read fresh each time so a backend
// that starts after Electron still works.
function readToken() {
  try {
    return fs.readFileSync(TOKEN_PATH, "utf8").trim();
  } catch {
    return "";
  }
}

ipcMain.handle("rove:get-token", readToken);

// The app only ever shows its own pages: no popups, no navigating away to the web.
function lockDown(win) {
  const allowed = isDev ? DEV_URL : "file://";
  win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  win.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith(allowed)) event.preventDefault();
  });
}
const isDev = process.env.ROVE_DEV === "1";

let mainWindow = null;
let tray = null;
let popover = null;
app.isQuitting = false;

function createWindow() {
  if (mainWindow) {
    mainWindow.show();
    mainWindow.focus();
    return;
  }

  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    title: "Rove",
    icon: path.join(__dirname, "assets", "icon.png"),
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      preload: path.join(__dirname, "preload.js"),
    },
  });
  lockDown(mainWindow);

  if (isDev) {
    mainWindow.loadURL(DEV_URL);
  } else {
    mainWindow.loadFile(PROD_ENTRY);
  }

  mainWindow.once("ready-to-show", () => mainWindow.show());

  mainWindow.on("close", (event) => {
    if (!app.isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

function createPopover() {
  popover = new BrowserWindow({
    width: 340,
    height: 150,
    show: false,
    frame: false,
    transparent: true,
    resizable: false,
    movable: false,
    focusable: false,
    skipTaskbar: true,
    hasShadow: false,
    alwaysOnTop: true,
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true, preload: path.join(__dirname, "preload.js") },
  });
  lockDown(popover);
  popover.setAlwaysOnTop(true, "screen-saver");
  popover.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });

  if (isDev) {
    popover.loadURL(`${DEV_URL}/popover`);
  } else {
    popover.loadFile(POPOVER_ENTRY);
  }
}

function showPopover() {
  if (!popover) return;
  const { workArea } = screen.getDisplayNearestPoint(screen.getCursorScreenPoint());
  const { width } = popover.getBounds();
  popover.setPosition(Math.round(workArea.x + (workArea.width - width) / 2), workArea.y + 48);
  popover.showInactive();
}

// Backend owns the Command-hold state machine; this only mirrors it into show/hide.
async function watchQuickEvents() {
  while (!app.isQuitting) {
    try {
      const response = await fetch(QUICK_EVENTS_URL, { headers: { "X-Rove-Token": readToken() } });
      if (!response.ok) throw new Error(`quick events ${response.status}`);
      const decoder = new TextDecoder();
      let buffer = "";
      for await (const chunk of response.body) {
        buffer += decoder.decode(chunk, { stream: true });
        const frames = buffer.split("\n\n");
        buffer = frames.pop();
        for (const frame of frames) {
          if (!frame.startsWith("data: ")) continue;
          const { state } = JSON.parse(frame.slice(6));
          if (state === "idle") popover?.hide();
          else showPopover();
          // Menu-bar feedback while a Command-hold task is active.
          tray?.setTitle(state === "idle" ? "" : ` ${state === "executing" ? "working" : state}`);
        }
      }
    } catch {
      // backend not up yet; retry below
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
}

function createTray() {
  const icon = nativeImage.createFromPath(path.join(__dirname, "assets", "trayTemplate.png"));
  icon.setTemplateImage(true);
  tray = new Tray(icon);
  tray.setToolTip("Rove");

  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: "Open Rove", click: createWindow },
      { type: "separator" },
      {
        label: "Quit Rove",
        click: () => {
          app.isQuitting = true;
          app.quit();
        },
      },
    ]),
  );

  tray.on("click", createWindow);
}

function createAppMenu() {
  const template = [
    {
      label: "Rove",
      submenu: [
        { role: "about" },
        { type: "separator" },
        { role: "hide" },
        { role: "hideOthers" },
        { type: "separator" },
        {
          label: "Quit Rove",
          accelerator: "Cmd+Q",
          click: () => {
            app.isQuitting = true;
            app.quit();
          },
        },
      ],
    },
    {
      label: "Edit",
      submenu: [
        { role: "undo" },
        { role: "redo" },
        { type: "separator" },
        { role: "cut" },
        { role: "copy" },
        { role: "paste" },
        { role: "selectAll" },
      ],
    },
  ];

  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

app.whenReady().then(() => {
  ensureBackend();
  createAppMenu();
  createTray();
  createWindow();
  createPopover();
  watchQuickEvents();

  app.on("activate", createWindow);
});

app.on("before-quit", () => {
  app.isQuitting = true;
  if (backend) backend.kill();
});

app.on("window-all-closed", () => {
  // ponytail: stay alive in the tray on macOS; real quit only via Quit Rove / Cmd+Q.
});
