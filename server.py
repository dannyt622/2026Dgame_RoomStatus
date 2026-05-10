from __future__ import annotations

import json
import mimetypes
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("DB_PATH", BASE_DIR / "room_status.sqlite3"))
STATIC_DIR = BASE_DIR / "static"
ROOM_NAMES = [
    "助手的車",
    "教授房間",
    "助手房間",
    "教授老婆房間",
    "男學生房間",
    "秘書房間",
]
ROOM_COUNT = len(ROOM_NAMES)
SESSION_MINUTES = 15


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def isoformat(value: datetime) -> str:
    return value.isoformat()


def get_db() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with get_db() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('available', 'in_use')),
                started_at TEXT,
                ends_at TEXT
            )
            """
        )
        for room_id, room_name in enumerate(ROOM_NAMES, start=1):
            db.execute(
                """
                INSERT OR IGNORE INTO rooms (id, name, status, started_at, ends_at)
                VALUES (?, ?, 'available', NULL, NULL)
                """,
                (room_id, room_name),
            )
            db.execute(
                "UPDATE rooms SET name = ? WHERE id = ?",
                (room_name, room_id),
            )


def expire_finished_rooms(db: sqlite3.Connection) -> None:
    now = isoformat(utc_now())
    db.execute(
        """
        UPDATE rooms
        SET status = 'available', started_at = NULL, ends_at = NULL
        WHERE status = 'in_use' AND ends_at <= ?
        """,
        (now,),
    )


def row_to_room(row: sqlite3.Row) -> dict[str, object]:
    remaining_seconds = 0
    if row["status"] == "in_use" and row["ends_at"]:
        ends_at = datetime.fromisoformat(row["ends_at"])
        remaining_seconds = max(0, int((ends_at - utc_now()).total_seconds()))

    return {
        "id": row["id"],
        "name": row["name"],
        "status": row["status"],
        "started_at": row["started_at"],
        "ends_at": row["ends_at"],
        "remaining_seconds": remaining_seconds,
    }


def get_rooms() -> list[dict[str, object]]:
    with get_db() as db:
        expire_finished_rooms(db)
        rows = db.execute("SELECT * FROM rooms ORDER BY id").fetchall()
    return [row_to_room(row) for row in rows]


def get_room(room_id: int) -> dict[str, object] | None:
    with get_db() as db:
        expire_finished_rooms(db)
        row = db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    return row_to_room(row) if row else None


def start_room(room_id: int) -> dict[str, object] | None:
    now = utc_now()
    ends_at = now + timedelta(minutes=SESSION_MINUTES)
    with get_db() as db:
        expire_finished_rooms(db)
        row = db.execute("SELECT status FROM rooms WHERE id = ?", (room_id,)).fetchone()
        if row is None:
            return None
        if row["status"] == "available":
            db.execute(
                """
                UPDATE rooms
                SET status = 'in_use', started_at = ?, ends_at = ?
                WHERE id = ?
                """,
                (isoformat(now), isoformat(ends_at), room_id),
            )
        row = db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    return row_to_room(row)


def end_room(room_id: int) -> dict[str, object] | None:
    with get_db() as db:
        expire_finished_rooms(db)
        row = db.execute("SELECT id FROM rooms WHERE id = ?", (room_id,)).fetchone()
        if row is None:
            return None
        db.execute(
            """
            UPDATE rooms
            SET status = 'available', started_at = NULL, ends_at = NULL
            WHERE id = ?
            """,
            (room_id,),
        )
        row = db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    return row_to_room(row)


def page_template(title: str, body_class: str, app_config: dict[str, object]) -> bytes:
    config_json = json.dumps(app_config)
    html = f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#f5f7f8">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-title" content="房間狀態">
  <title>{title}</title>
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body class="{body_class}">
  <main class="shell">
    <header class="topbar">
      <div>
        <p class="eyebrow">活動房間</p>
        <h1>{title}</h1>
      </div>
      <p class="sync" id="syncStatus">連線中</p>
    </header>
    <section id="app" aria-live="polite"></section>
  </main>
  <script>window.ROOM_TIMER_CONFIG = {config_json};</script>
  <script src="/static/app.js"></script>
</body>
</html>
"""
    return html.encode("utf-8")


class RoomTimerHandler(BaseHTTPRequestHandler):
    server_version = "RoomTimer/1.0"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self.send_html(
                page_template(
                    "房間狀態",
                    "dashboard-page",
                    {"page": "dashboard"},
                )
            )
            return

        staff_prefix = "/staff/room/"
        if path.startswith(staff_prefix):
            room_text = path.removeprefix(staff_prefix).strip("/")
            if room_text.isdigit():
                room_id = int(room_text)
                if 1 <= room_id <= ROOM_COUNT:
                    self.send_html(
                        page_template(
                            ROOM_NAMES[room_id - 1],
                            "staff-page",
                            {"page": "staff", "roomId": room_id},
                        )
                    )
                    return
            self.send_error(HTTPStatus.NOT_FOUND, "Room not found")
            return

        if path == "/api/rooms":
            self.send_json({"rooms": get_rooms()})
            return

        if path.startswith("/api/rooms/"):
            room_id = self.extract_room_id(path)
            if room_id is None:
                self.send_error(HTTPStatus.NOT_FOUND, "Room not found")
                return
            room = get_room(room_id)
            if room is None:
                self.send_error(HTTPStatus.NOT_FOUND, "Room not found")
                return
            self.send_json({"room": room})
            return

        if path.startswith("/static/"):
            self.send_static(path)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Page not found")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path.endswith("/start"):
            room_id = self.extract_room_id(path.removesuffix("/start"))
            room = start_room(room_id) if room_id is not None else None
        elif path.endswith("/end"):
            room_id = self.extract_room_id(path.removesuffix("/end"))
            room = end_room(room_id) if room_id is not None else None
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Action not found")
            return

        if room is None:
            self.send_error(HTTPStatus.NOT_FOUND, "Room not found")
            return
        self.send_json({"room": room})

    def extract_room_id(self, path: str) -> int | None:
        parts = path.strip("/").split("/")
        if len(parts) != 3 or parts[:2] != ["api", "rooms"]:
            return None
        if not parts[2].isdigit():
            return None
        room_id = int(parts[2])
        return room_id if 1 <= room_id <= ROOM_COUNT else None

    def send_html(self, content: bytes) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, payload: dict[str, object]) -> None:
        content = json.dumps(payload).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_static(self, path: str) -> None:
        relative_path = path.removeprefix("/static/").strip("/")
        file_path = (STATIC_DIR / relative_path).resolve()
        if not file_path.is_file() or STATIC_DIR.resolve() not in file_path.parents:
            self.send_error(HTTPStatus.NOT_FOUND, "Asset not found")
            return

        content = file_path.read_bytes()
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")


def main() -> None:
    init_db()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8001"))
    server = ThreadingHTTPServer((host, port), RoomTimerHandler)
    print(f"Room timer running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
