const { app, BrowserWindow, Tray, Menu, nativeImage, screen } = require("electron");
const path = require("path");

const DEV_URL = "http://localhost:3000";
const PROD_ENTRY = path.join(__dirname, "..", "frontend", "out", "index.html");
const POPOVER_ENTRY = path.join(__dirname, "..", "frontend", "out", "popover.html");
const QUICK_EVENTS_URL = "http://127.0.0.1:8000/api/quick/events";
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
    },
  });

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
    webPreferences: { contextIsolation: true, nodeIntegration: false },
  });
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
      const response = await fetch(QUICK_EVENTS_URL);
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
  createAppMenu();
  createTray();
  createWindow();
  createPopover();
  watchQuickEvents();

  app.on("activate", createWindow);
});

app.on("before-quit", () => {
  app.isQuitting = true;
});

app.on("window-all-closed", () => {
  // ponytail: stay alive in the tray on macOS; real quit only via Quit Rove / Cmd+Q.
});
