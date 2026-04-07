from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

from .config import load_db_config


class Database:
    def __init__(self) -> None:
        self.config = load_db_config()
        self.engine = self.config.get("engine", "sqlite").lower()
        self._initialize_database()

    @contextmanager
    def connect(self) -> Iterator:
        if self.engine == "mysql":
            try:
                import pymysql
            except ImportError as exc:
                raise RuntimeError(
                    "MySQL support requires the 'pymysql' package. Install dependencies first."
                ) from exc

            connection = pymysql.connect(
                host=self.config.get("host", "127.0.0.1"),
                port=int(self.config.get("port", 3306)),
                user=self.config.get("user", "root"),
                password=self.config.get("password", ""),
                database=self.config.get("database", "gym_qr_system"),
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=False,
            )
        else:
            connection = sqlite3.connect(self.config["sqlite_path"])
            connection.row_factory = sqlite3.Row

        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize_database(self) -> None:
        if self.engine == "mysql":
            members_sql = """
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTO_INCREMENT,
                full_name VARCHAR(255) NOT NULL,
                phone VARCHAR(50),
                email VARCHAR(255),
                qr_token VARCHAR(255) NOT NULL UNIQUE,
                qr_image_path TEXT NOT NULL,
                credits INTEGER NOT NULL DEFAULT 0,
                last_paid_scan_date VARCHAR(10),
                created_at VARCHAR(50) NOT NULL
            )
            """
            attendance_sql = """
            CREATE TABLE IF NOT EXISTS attendance_logs (
                id INTEGER PRIMARY KEY AUTO_INCREMENT,
                member_id INTEGER,
                scan_token VARCHAR(255) NOT NULL,
                status VARCHAR(50) NOT NULL,
                credits_before INTEGER NOT NULL DEFAULT 0,
                credits_after INTEGER NOT NULL DEFAULT 0,
                notes TEXT,
                created_at VARCHAR(50) NOT NULL,
                FOREIGN KEY (member_id) REFERENCES members(id)
            )
            """
        else:
            members_sql = """
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name VARCHAR(255) NOT NULL,
                phone VARCHAR(50),
                email VARCHAR(255),
                qr_token VARCHAR(255) NOT NULL UNIQUE,
                qr_image_path TEXT NOT NULL,
                credits INTEGER NOT NULL DEFAULT 0,
                last_paid_scan_date VARCHAR(10),
                created_at VARCHAR(50) NOT NULL
            )
            """
            attendance_sql = """
            CREATE TABLE IF NOT EXISTS attendance_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_id INTEGER,
                scan_token VARCHAR(255) NOT NULL,
                status VARCHAR(50) NOT NULL,
                credits_before INTEGER NOT NULL DEFAULT 0,
                credits_after INTEGER NOT NULL DEFAULT 0,
                notes TEXT,
                created_at VARCHAR(50) NOT NULL,
                FOREIGN KEY (member_id) REFERENCES members(id)
            )
            """

        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(members_sql)
            cursor.execute(attendance_sql)
            self._ensure_members_columns(cursor)

    def _ensure_members_columns(self, cursor) -> None:
        if self.engine == "mysql":
            cursor.execute("SHOW COLUMNS FROM members LIKE 'last_paid_scan_date'")
            has_column = cursor.fetchone() is not None
            if not has_column:
                cursor.execute("ALTER TABLE members ADD COLUMN last_paid_scan_date VARCHAR(10) NULL")
        else:
            cursor.execute("PRAGMA table_info(members)")
            columns = [row[1] for row in cursor.fetchall()]
            if "last_paid_scan_date" not in columns:
                cursor.execute("ALTER TABLE members ADD COLUMN last_paid_scan_date VARCHAR(10)")

    def create_member(
        self,
        full_name: str,
        phone: str,
        email: str,
        qr_token: str,
        qr_image_path: str,
        initial_credits: int,
    ) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        sql = """
        INSERT INTO members (full_name, phone, email, qr_token, qr_image_path, credits, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            full_name,
            phone,
            email,
            qr_token,
            qr_image_path,
            initial_credits,
            now,
        )

        if self.engine == "mysql":
            sql = sql.replace("?", "%s")

        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(sql, params)
            return cursor.lastrowid

    def get_members(self) -> list[dict]:
        sql = "SELECT * FROM members ORDER BY id DESC"
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(sql)
            return [dict(row) for row in cursor.fetchall()]

    def get_member_count(self) -> int:
        sql = "SELECT COUNT(*) AS total FROM members"
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(sql)
            row = cursor.fetchone()
            return int(dict(row)["total"])

    def get_member_by_id(self, member_id: int) -> dict | None:
        sql = "SELECT * FROM members WHERE id = ?"
        if self.engine == "mysql":
            sql = sql.replace("?", "%s")

        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(sql, (member_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_member_by_qr_token(self, token: str) -> dict | None:
        sql = "SELECT * FROM members WHERE qr_token = ?"
        if self.engine == "mysql":
            sql = sql.replace("?", "%s")

        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(sql, (token,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def add_credits(self, member_id: int, amount: int) -> None:
        sql = "UPDATE members SET credits = credits + ? WHERE id = ?"
        if self.engine == "mysql":
            sql = sql.replace("?", "%s")

        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(sql, (amount, member_id))

    def get_today_successful_check_in(self, member_id: int) -> dict | None:
        day_prefix = datetime.now().strftime("%Y-%m-%d")
        sql = """
        SELECT *
        FROM attendance_logs
        WHERE member_id = ?
          AND status IN ('approved', 'already_scanned')
          AND created_at LIKE ?
        ORDER BY id DESC
        LIMIT 1
        """
        params = (member_id, f"{day_prefix}%")
        if self.engine == "mysql":
            sql = sql.replace("?", "%s")

        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(sql, params)
            row = cursor.fetchone()
            return dict(row) if row else None

    def log_attendance(
        self,
        member_id: int | None,
        scan_token: str,
        status: str,
        credits_before: int,
        credits_after: int,
        notes: str,
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        sql = """
        INSERT INTO attendance_logs (
            member_id, scan_token, status, credits_before, credits_after, notes, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            member_id,
            scan_token,
            status,
            credits_before,
            credits_after,
            notes,
            now,
        )

        if self.engine == "mysql":
            sql = sql.replace("?", "%s")

        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(sql, params)

    def consume_credit_for_check_in(self, member_id: int) -> tuple[bool, dict | None, str]:
        today = datetime.now().strftime("%Y-%m-%d")
        member = self.get_member_by_id(member_id)
        if not member:
            return False, None, "Member not found."

        credits_before = int(member["credits"])

        with self.connect() as connection:
            cursor = connection.cursor()
            update_sql = """
            UPDATE members
            SET credits = credits - 1, last_paid_scan_date = ?
            WHERE id = ?
              AND credits > 0
              AND (last_paid_scan_date IS NULL OR last_paid_scan_date <> ?)
            """
            update_params = (today, member_id, today)
            if self.engine == "mysql":
                update_sql = update_sql.replace("?", "%s")

            cursor.execute(update_sql, update_params)
            changed_rows = cursor.rowcount

            fetch_sql = "SELECT * FROM members WHERE id = ?"
            if self.engine == "mysql":
                fetch_sql = fetch_sql.replace("?", "%s")
            cursor.execute(fetch_sql, (member_id,))
            current = dict(cursor.fetchone())

            if changed_rows == 1:
                self._log_attendance_with_connection(
                    connection=connection,
                    member_id=member_id,
                    scan_token=current["qr_token"],
                    status="approved",
                    credits_before=credits_before,
                    credits_after=int(current["credits"]),
                    notes="Credit deducted successfully.",
                )
                return True, current, "Credit deducted successfully."

            current_credits = int(current["credits"])
            if current.get("last_paid_scan_date") == today:
                self._log_attendance_with_connection(
                    connection=connection,
                    member_id=member_id,
                    scan_token=current["qr_token"],
                    status="already_scanned",
                    credits_before=current_credits,
                    credits_after=current_credits,
                    notes="Already scanned today. No credit deducted.",
                )
                return True, current, "Already scanned today. No credit deducted."

            self._log_attendance_with_connection(
                connection=connection,
                member_id=member_id,
                scan_token=current["qr_token"],
                status="denied",
                credits_before=current_credits,
                credits_after=current_credits,
                notes="No remaining credits.",
            )
            return False, current, "No remaining credits."

    def _log_attendance_with_connection(
        self,
        connection,
        member_id: int | None,
        scan_token: str,
        status: str,
        credits_before: int,
        credits_after: int,
        notes: str,
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        sql = """
        INSERT INTO attendance_logs (
            member_id, scan_token, status, credits_before, credits_after, notes, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            member_id,
            scan_token,
            status,
            credits_before,
            credits_after,
            notes,
            now,
        )
        if self.engine == "mysql":
            sql = sql.replace("?", "%s")

        cursor = connection.cursor()
        cursor.execute(sql, params)

    def get_dashboard_stats(self) -> dict:
        day_prefix = datetime.now().strftime("%Y-%m-%d")
        member_sql = "SELECT COUNT(*) AS total_members FROM members"
        credits_sql = "SELECT COALESCE(SUM(credits), 0) AS total_credits FROM members"
        low_credit_sql = "SELECT COUNT(*) AS low_credit_members FROM members WHERE credits <= 2"
        attendance_sql = """
        SELECT COUNT(*) AS today_entries
        FROM attendance_logs
        WHERE status = 'approved'
          AND created_at LIKE ?
        """

        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(member_sql)
            total_members = int(dict(cursor.fetchone())["total_members"])

            cursor.execute(credits_sql)
            total_credits = int(dict(cursor.fetchone())["total_credits"])

            cursor.execute(low_credit_sql)
            low_credit_members = int(dict(cursor.fetchone())["low_credit_members"])

            if self.engine == "mysql":
                attendance_sql = attendance_sql.replace("?", "%s")

            cursor.execute(attendance_sql, (f"{day_prefix}%",))
            today_entries = int(dict(cursor.fetchone())["today_entries"])

        return {
            "total_members": total_members,
            "total_credits": total_credits,
            "low_credit_members": low_credit_members,
            "today_entries": today_entries,
        }

    def get_attendance_logs(self) -> list[dict]:
        sql = """
        SELECT
            attendance_logs.id,
            attendance_logs.scan_token,
            attendance_logs.status,
            attendance_logs.credits_before,
            attendance_logs.credits_after,
            attendance_logs.notes,
            attendance_logs.created_at,
            members.full_name
        FROM attendance_logs
        LEFT JOIN members ON members.id = attendance_logs.member_id
        ORDER BY attendance_logs.id DESC
        """
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(sql)
            return [dict(row) for row in cursor.fetchall()]
