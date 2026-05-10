const config = window.ROOM_TIMER_CONFIG;
const app = document.querySelector("#app");
const syncStatus = document.querySelector("#syncStatus");
let rooms = [];
let activeRoom = null;
let renderTimer = null;
let pollTimer = null;

function formatTime(totalSeconds) {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}:${String(remainder).padStart(2, "0")}`;
}

function secondsUntil(endsAt) {
  if (!endsAt) {
    return 0;
  }
  return Math.max(0, Math.floor((new Date(endsAt).getTime() - Date.now()) / 1000));
}

function roomIsInUse(room) {
  return room.status === "in_use" && secondsUntil(room.ends_at) > 0;
}

function setSync(text) {
  syncStatus.textContent = text;
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    cache: "no-store",
    headers: { "Accept": "application/json" },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

function dashboardMarkup() {
  return `
    <div class="room-grid">
      ${rooms.map((room) => {
        const inUse = roomIsInUse(room);
        return `
          <article class="room-card ${inUse ? "is-busy" : "is-free"}">
            <div class="room-card__header">
              <h2>${room.name}</h2>
              <span class="status-pill">${inUse ? "使用中" : "可使用"}</span>
            </div>
            <p class="timer-label">${inUse ? "剩餘時間" : "狀態"}</p>
            <p class="timer ${inUse ? "" : "timer--muted"}">
              ${inUse ? formatTime(secondsUntil(room.ends_at)) : "可使用"}
            </p>
          </article>
        `;
      }).join("")}
    </div>
  `;
}

function staffMarkup() {
  if (!activeRoom) {
    return `<section class="focus-panel"><p class="loading">載入房間中</p></section>`;
  }

  const inUse = roomIsInUse(activeRoom);
  return `
    <section class="focus-panel ${inUse ? "is-busy" : "is-free"}">
      <div class="focus-panel__status">
        <span class="status-pill">${inUse ? "使用中" : "可使用"}</span>
      </div>
      <h2>${activeRoom.name}</h2>
      <p class="focus-label">${inUse ? "剩餘時間" : "狀態"}</p>
      <p class="focus-timer">${inUse ? formatTime(secondsUntil(activeRoom.ends_at)) : "可使用"}</p>
      <div class="actions">
        ${inUse
          ? `<button class="button button--danger" type="button" data-action="end">提早結束</button>`
          : `<button class="button" type="button" data-action="start">開始 15 分鐘</button>`}
      </div>
    </section>
  `;
}

function render() {
  app.innerHTML = config.page === "dashboard" ? dashboardMarkup() : staffMarkup();
}

async function loadDashboard() {
  const data = await requestJson("/api/rooms");
  rooms = data.rooms;
  setSync(`已更新 ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`);
  render();
}

async function loadStaffRoom() {
  const data = await requestJson(`/api/rooms/${config.roomId}`);
  activeRoom = data.room;
  setSync(`已更新 ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`);
  render();
}

async function startRoom() {
  const button = app.querySelector("[data-action='start']");
  if (button) {
    button.disabled = true;
  }
  const data = await requestJson(`/api/rooms/${config.roomId}/start`, { method: "POST" });
  activeRoom = data.room;
  render();
}

async function endRoom() {
  const button = app.querySelector("[data-action='end']");
  if (button) {
    button.disabled = true;
  }
  const data = await requestJson(`/api/rooms/${config.roomId}/end`, { method: "POST" });
  activeRoom = data.room;
  render();
}

async function poll() {
  try {
    if (config.page === "dashboard") {
      await loadDashboard();
    } else {
      await loadStaffRoom();
    }
  } catch (error) {
    console.error(error);
    setSync("連線中斷");
  }
}

app.addEventListener("click", (event) => {
  const action = event.target.closest("[data-action]")?.dataset.action;
  if (action === "start") {
    startRoom().catch((error) => {
      console.error(error);
      setSync("開始失敗");
      poll();
    });
  }
  if (action === "end") {
    endRoom().catch((error) => {
      console.error(error);
      setSync("結束失敗");
      poll();
    });
  }
});

renderTimer = window.setInterval(render, 1000);
pollTimer = window.setInterval(poll, 3000);
poll();
