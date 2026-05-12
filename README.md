# Event Room Timer

A small, dependency-free Python website for managing five 15-minute event rooms.

## Run

```bash
python3 server.py
```

Open:

- Dashboard: <http://127.0.0.1:8001/>
- Staff room pages: <http://127.0.0.1:8001/staff/room/1> through `/staff/room/5`

Room state is stored in `room_status.sqlite3`. The app stores `started_at` and `ends_at`, then calculates remaining time from the current time on each request.

## Phone usage

Participants should open the public dashboard URL to see all room statuses.

Staff should open only their assigned room URL:

- Room 1: `/staff/room/1`
- Room 2: `/staff/room/2`
- Room 3: `/staff/room/3`
- Room 4: `/staff/room/4`
- Room 5: `/staff/room/5`

## Deploy on Render

Choose **Web Services**.

- Runtime: Python
- Build command: `python3 -m py_compile server.py`
- Start command: `python3 server.py`
- Environment variable: `HOST=0.0.0.0`

For persistent SQLite storage, add a Render disk mounted at `/var/data`, then add:

- Environment variable: `DB_PATH=/var/data/room_status.sqlite3`
