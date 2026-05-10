from __future__ import annotations

import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

import server


class RoomTimerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = server.DB_PATH
        server.DB_PATH = Path(self.temp_dir.name) / "test.sqlite3"
        server.init_db()

    def tearDown(self) -> None:
        server.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_initializes_six_available_rooms(self) -> None:
        rooms = server.get_rooms()
        self.assertEqual(len(rooms), 6)
        self.assertEqual(
            [room["name"] for room in rooms],
            [
                "助手的車",
                "教授房間",
                "助手房間",
                "教授老婆房間",
                "男學生房間",
                "秘書房間",
            ],
        )
        self.assertTrue(all(room["status"] == "available" for room in rooms))

    def test_start_sets_timestamps_and_end_early_clears_them(self) -> None:
        started = server.start_room(1)

        self.assertEqual(started["status"], "in_use")
        self.assertIsNotNone(started["started_at"])
        self.assertIsNotNone(started["ends_at"])
        self.assertGreater(started["remaining_seconds"], 890)

        ended = server.end_room(1)
        self.assertEqual(ended["status"], "available")
        self.assertIsNone(ended["started_at"])
        self.assertIsNone(ended["ends_at"])

    def test_expired_room_becomes_available_from_ends_at(self) -> None:
        now = server.utc_now()
        with server.get_db() as db:
            db.execute(
                """
                UPDATE rooms
                SET status = 'in_use', started_at = ?, ends_at = ?
                WHERE id = 2
                """,
                (
                    server.isoformat(now - timedelta(minutes=20)),
                    server.isoformat(now - timedelta(minutes=5)),
                ),
            )

        room = server.get_room(2)

        self.assertEqual(room["status"], "available")
        self.assertIsNone(room["started_at"])
        self.assertIsNone(room["ends_at"])


if __name__ == "__main__":
    unittest.main()
