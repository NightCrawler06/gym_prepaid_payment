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
            self._ensure_mysql_database()
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
            self._ensure_mysql_database()

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

    def _ensure_mysql_database(self) -> None:
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
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
        )

        try:
            cursor = connection.cursor()
            database_name = self.config.get("database", "gym_qr_system")
            safe_database_name = database_name.replace("`", "``")
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{safe_database_name}`")
        finally:
            connection.close()

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
        member = self.get_member_by_id(member_id)
        if not member:
            return False, None, "Member not found."

        existing_check_in = self.get_today_successful_check_in(member_id)
        if existing_check_in:
            current_credits = int(member["credits"])
            self.log_attendance(
                member_id=member_id,
                scan_token=member["qr_token"],
                status="already_scanned",
                credits_before=current_credits,
                credits_after=current_credits,
                notes="Already scanned today. No credit deducted.",
            )
            return True, member, "Already scanned today. No credit deducted."

        credits_before = int(member["credits"])
        if credits_before <= 0:
            self.log_attendance(
                member_id=member_id,
                scan_token=member["qr_token"],
                status="denied",
                credits_before=credits_before,
                credits_after=credits_before,
                notes="No remaining credits.",
            )
            return False, member, "No remaining credits."

        sql = "UPDATE members SET credits = credits - 1 WHERE id = ?"
        if self.engine == "mysql":
            sql = sql.replace("?", "%s")

        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(sql, (member_id,))

        updated = self.get_member_by_id(member_id)
        self.log_attendance(
            member_id=member_id,
            scan_token=member["qr_token"],
            status="approved",
            credits_before=credits_before,
            credits_after=int(updated["credits"]),
            notes="Entry approved.",
        )
        return True, updated, "Entry approved."

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
