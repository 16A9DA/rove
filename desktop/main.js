const { app, BrowserWindow, Tray, Menu, nativeImage } = require("electron");
const path = require("path");

const DEV_URL = "http://localhost:3000";
const PROD_ENTRY = path.join(__dirname, "..", "frontend", "out", "index.html");
const isDev = process.env.ROVE_DEV === "1";

let mainWindow = null;
let tray = null;
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

  app.on("activate", createWindow);
});

app.on("before-quit", () => {
  app.isQuitting = true;
});

app.on("window-all-closed", () => {
  // ponytail: stay alive in the tray on macOS; real quit only via Quit Rove / Cmd+Q.
});
