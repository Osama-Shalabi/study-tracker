import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class DataStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_schema(self):
        conn = self._connect()
        cur = conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                color TEXT NOT NULL DEFAULT '#7ac7ff',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id INTEGER NOT NULL,
                minutes INTEGER NOT NULL,
                occurred_at TEXT NOT NULL,
                FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS chapters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                done INTEGER NOT NULL DEFAULT 0,
                notes TEXT DEFAULT '',
                FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE
            );
            """
        )
        conn.commit()
        conn.close()

    # Subjects
    def list_subjects(self) -> List[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM subjects ORDER BY created_at DESC").fetchall()

    def create_subject(self, name: str, color: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO subjects (name, color) VALUES (?, ?)",
                (name.strip(), color.strip()),
            )
            conn.commit()
            return cur.lastrowid

    def delete_subject(self, subject_id: int):
        with self._connect() as conn:
            conn.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
            conn.commit()

    def rename_subject(self, subject_id: int, new_name: str):
        with self._connect() as conn:
            conn.execute("UPDATE subjects SET name = ? WHERE id = ?", (new_name.strip(), subject_id))
            conn.commit()

    # Sessions
    def log_session(self, subject_id: int, minutes: int, when: Optional[datetime] = None):
        when = when or datetime.utcnow()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (subject_id, minutes, occurred_at) VALUES (?, ?, ?)",
                (subject_id, minutes, when.isoformat()),
            )
            conn.commit()

    def get_stats(self) -> Dict[str, int]:
        now = datetime.utcnow()
        day_start = datetime(now.year, now.month, now.day)
        week_start = day_start - timedelta(days=(day_start.weekday() + 1) % 7)
        month_start = datetime(now.year, now.month, 1)

        with self._connect() as conn:
            cur = conn.cursor()

            def total_since(ts: datetime) -> int:
                return cur.execute(
                    "SELECT COALESCE(SUM(minutes),0) FROM sessions WHERE occurred_at >= ?",
                    (ts.isoformat(),),
                ).fetchone()[0]

            day = total_since(day_start)
            week = total_since(week_start)
            month = total_since(month_start)

            # bar chart: this week Sunday -> Saturday
            bars: List[Tuple[str, int]] = []
            sunday_start = day_start - timedelta(days=(day_start.weekday() + 1) % 7)
            for offset in range(7):
                start = sunday_start + timedelta(days=offset)
                end = start + timedelta(days=1)
                total = cur.execute(
                    "SELECT COALESCE(SUM(minutes),0) FROM sessions WHERE occurred_at >= ? AND occurred_at < ?",
                    (start.isoformat(), end.isoformat()),
                ).fetchone()[0]
                label = start.strftime("%a")
                bars.append((label, total))

            # monthly totals, current month first then previous months
            month_cards: List[Tuple[str, int]] = []
            m_start = month_start
            for _ in range(3):
                m_end = (m_start + timedelta(days=32)).replace(day=1)
                total = cur.execute(
                    "SELECT COALESCE(SUM(minutes),0) FROM sessions WHERE occurred_at >= ? AND occurred_at < ?",
                    (m_start.isoformat(), m_end.isoformat()),
                ).fetchone()[0]
                month_cards.append((m_start.strftime("%b"), total))
                m_start = (m_start - timedelta(days=1)).replace(day=1)

        return {
            "day": day,
            "week": week,
            "month": month,
            "bars": bars,
            "month_cards": month_cards,
        }

    # Chapters
    def list_chapters(self, subject_id: int) -> List[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM chapters WHERE subject_id = ? ORDER BY position ASC, id ASC",
                (subject_id,),
            ).fetchall()

    def add_chapter(self, subject_id: int, title: str):
        with self._connect() as conn:
            max_pos = conn.execute(
                "SELECT COALESCE(MAX(position),0) FROM chapters WHERE subject_id = ?",
                (subject_id,),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO chapters (subject_id, title, position) VALUES (?, ?, ?)",
                (subject_id, title.strip(), max_pos + 1),
            )
            conn.commit()

    def toggle_chapter(self, chapter_id: int, done: bool):
        with self._connect() as conn:
            conn.execute("UPDATE chapters SET done = ? WHERE id = ?", (1 if done else 0, chapter_id))
            conn.commit()

    def update_notes(self, chapter_id: int, notes: str):
        with self._connect() as conn:
            conn.execute("UPDATE chapters SET notes = ? WHERE id = ?", (notes, chapter_id))
            conn.commit()

    def delete_chapter(self, chapter_id: int):
        with self._connect() as conn:
            conn.execute("DELETE FROM chapters WHERE id = ?", (chapter_id,))
            conn.commit()
