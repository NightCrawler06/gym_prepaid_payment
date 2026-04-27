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

        members_sql = """
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY {primary_key},
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
            id INTEGER PRIMARY KEY {primary_key},
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
        topups_sql = """
        CREATE TABLE IF NOT EXISTS credit_topups (
            id INTEGER PRIMARY KEY {primary_key},
            member_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            notes TEXT,
            created_at VARCHAR(50) NOT NULL,
            FOREIGN KEY (member_id) REFERENCES members(id)
        )
        """
        audit_sql = """
        CREATE TABLE IF NOT EXISTS credit_audit (
            id INTEGER PRIMARY KEY {primary_key},
            member_id INTEGER,
            source_type VARCHAR(50) NOT NULL,
            source_id INTEGER,
            credit_change INTEGER NOT NULL DEFAULT 0,
            balance_after INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            created_at VARCHAR(50) NOT NULL,
            FOREIGN KEY (member_id) REFERENCES members(id)
        )
        """
        reports_sql = """
        CREATE TABLE IF NOT EXISTS daily_reports (
            report_date VARCHAR(10) PRIMARY KEY,
            total_members INTEGER NOT NULL DEFAULT 0,
            total_credits INTEGER NOT NULL DEFAULT 0,
            approved_entries INTEGER NOT NULL DEFAULT 0,
            topup_amount INTEGER NOT NULL DEFAULT 0,
            generated_at VARCHAR(50) NOT NULL
        )
        """

        primary_key = "AUTO_INCREMENT" if self.engine == "mysql" else "AUTOINCREMENT"
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(members_sql.format(primary_key=primary_key))
            cursor.execute(attendance_sql.format(primary_key=primary_key))
            cursor.execute(topups_sql.format(primary_key=primary_key))
            cursor.execute(audit_sql.format(primary_key=primary_key))
            cursor.execute(reports_sql)
            self._ensure_members_columns(cursor)

            if self.engine == "mysql":
                self._initialize_mysql_adbms_objects(connection)
            else:
                self._initialize_sqlite_support(cursor)

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

    def _initialize_sqlite_support(self, cursor) -> None:
        cursor.execute("DROP VIEW IF EXISTS vw_member_credit_summary")
        cursor.execute(
            """
            CREATE VIEW vw_member_credit_summary AS
            SELECT
                members.id,
                members.full_name,
                members.phone,
                members.email,
                members.qr_token,
                members.qr_image_path,
                members.credits,
                members.last_paid_scan_date,
                members.created_at,
                latest_scan.last_scan_at,
                latest_topup.last_topup_at
            FROM members
            LEFT JOIN (
                SELECT member_id, MAX(created_at) AS last_scan_at
                FROM attendance_logs
                GROUP BY member_id
            ) AS latest_scan ON latest_scan.member_id = members.id
            LEFT JOIN (
                SELECT member_id, MAX(created_at) AS last_topup_at
                FROM credit_topups
                GROUP BY member_id
            ) AS latest_topup ON latest_topup.member_id = members.id
            """
        )

        cursor.execute("DROP VIEW IF EXISTS vw_transaction_history")
        cursor.execute(
            """
            CREATE VIEW vw_transaction_history AS
            SELECT
                attendance_logs.id,
                attendance_logs.member_id,
                attendance_logs.scan_token,
                attendance_logs.status,
                attendance_logs.credits_before,
                attendance_logs.credits_after,
                attendance_logs.notes,
                attendance_logs.created_at,
                members.full_name,
                members.phone,
                members.email
            FROM attendance_logs
            LEFT JOIN members ON members.id = attendance_logs.member_id
            """
        )

        cursor.execute("DROP VIEW IF EXISTS vw_topup_history")
        cursor.execute(
            """
            CREATE VIEW vw_topup_history AS
            SELECT
                credit_topups.id,
                credit_topups.member_id,
                credit_topups.amount,
                credit_topups.notes,
                credit_topups.created_at,
                members.full_name
            FROM credit_topups
            INNER JOIN members ON members.id = credit_topups.member_id
            """
        )

    def _initialize_mysql_adbms_objects(self, connection) -> None:
        cursor = connection.cursor()

        try:
            cursor.execute("SET GLOBAL event_scheduler = ON")
        except Exception:
            pass

        self._create_mysql_views(cursor)
        self._create_mysql_triggers(cursor)
        self._create_mysql_stored_procedures(cursor)
        self._create_mysql_event(cursor)

    def _create_mysql_views(self, cursor) -> None:
        cursor.execute("DROP VIEW IF EXISTS vw_member_credit_summary")
        cursor.execute(
            """
            CREATE VIEW vw_member_credit_summary AS
            SELECT
                members.id,
                members.full_name,
                members.phone,
                members.email,
                members.qr_token,
                members.qr_image_path,
                members.credits,
                members.last_paid_scan_date,
                members.created_at,
                latest_scan.last_scan_at,
                latest_topup.last_topup_at
            FROM members
            LEFT JOIN (
                SELECT member_id, MAX(created_at) AS last_scan_at
                FROM attendance_logs
                GROUP BY member_id
            ) AS latest_scan ON latest_scan.member_id = members.id
            LEFT JOIN (
                SELECT member_id, MAX(created_at) AS last_topup_at
                FROM credit_topups
                GROUP BY member_id
            ) AS latest_topup ON latest_topup.member_id = members.id
            """
        )

        cursor.execute("DROP VIEW IF EXISTS vw_transaction_history")
        cursor.execute(
            """
            CREATE VIEW vw_transaction_history AS
            SELECT
                attendance_logs.id,
                attendance_logs.member_id,
                attendance_logs.scan_token,
                attendance_logs.status,
                attendance_logs.credits_before,
                attendance_logs.credits_after,
                attendance_logs.notes,
                attendance_logs.created_at,
                members.full_name,
                members.phone,
                members.email
            FROM attendance_logs
            LEFT JOIN members ON members.id = attendance_logs.member_id
            """
        )

        cursor.execute("DROP VIEW IF EXISTS vw_topup_history")
        cursor.execute(
            """
            CREATE VIEW vw_topup_history AS
            SELECT
                credit_topups.id,
                credit_topups.member_id,
                credit_topups.amount,
                credit_topups.notes,
                credit_topups.created_at,
                members.full_name
            FROM credit_topups
            INNER JOIN members ON members.id = credit_topups.member_id
            """
        )

        cursor.execute("DROP VIEW IF EXISTS vw_dashboard_stats")
        cursor.execute(
            """
            CREATE VIEW vw_dashboard_stats AS
            SELECT
                (SELECT COUNT(*) FROM members) AS total_members,
                (SELECT COALESCE(SUM(credits), 0) FROM members) AS total_credits,
                (
                    SELECT COUNT(*)
                    FROM attendance_logs
                    WHERE status = 'approved'
                      AND LEFT(created_at, 10) = DATE_FORMAT(CURDATE(), '%Y-%m-%d')
                ) AS today_entries,
                (SELECT COUNT(*) FROM members WHERE credits <= 2) AS low_credit_members,
                (
                    SELECT COALESCE(SUM(amount), 0)
                    FROM credit_topups
                    WHERE LEFT(created_at, 10) = DATE_FORMAT(CURDATE(), '%Y-%m-%d')
                ) AS today_topups,
                (SELECT COUNT(*) FROM daily_reports) AS saved_daily_reports
            """
        )

    def _create_mysql_triggers(self, cursor) -> None:
        cursor.execute("DROP TRIGGER IF EXISTS trg_members_no_negative_credits")
        cursor.execute(
            """
            CREATE TRIGGER trg_members_no_negative_credits
            BEFORE UPDATE ON members
            FOR EACH ROW
            BEGIN
                IF NEW.credits < 0 THEN
                    SIGNAL SQLSTATE '45000'
                    SET MESSAGE_TEXT = 'Credits cannot be negative.';
                END IF;
            END
            """
        )

        cursor.execute("DROP TRIGGER IF EXISTS trg_credit_topups_after_insert")
        cursor.execute(
            """
            CREATE TRIGGER trg_credit_topups_after_insert
            AFTER INSERT ON credit_topups
            FOR EACH ROW
            INSERT INTO credit_audit (
                member_id,
                source_type,
                source_id,
                credit_change,
                balance_after,
                notes,
                created_at
            )
            SELECT
                NEW.member_id,
                'topup',
                NEW.id,
                NEW.amount,
                members.credits,
                COALESCE(NEW.notes, 'Top-up recorded.'),
                NEW.created_at
            FROM members
            WHERE members.id = NEW.member_id
            """
        )

        cursor.execute("DROP TRIGGER IF EXISTS trg_attendance_logs_after_insert")
        cursor.execute(
            """
            CREATE TRIGGER trg_attendance_logs_after_insert
            AFTER INSERT ON attendance_logs
            FOR EACH ROW
            INSERT INTO credit_audit (
                member_id,
                source_type,
                source_id,
                credit_change,
                balance_after,
                notes,
                created_at
            )
            SELECT
                NEW.member_id,
                'scan',
                NEW.id,
                NEW.credits_after - NEW.credits_before,
                NEW.credits_after,
                COALESCE(NEW.notes, 'Scan transaction recorded.'),
                NEW.created_at
            FROM members
            WHERE members.id = NEW.member_id
            """
        )

    def _create_mysql_stored_procedures(self, cursor) -> None:
        cursor.execute("DROP PROCEDURE IF EXISTS sp_register_member")
        cursor.execute(
            """
            CREATE PROCEDURE sp_register_member(
                IN p_full_name VARCHAR(255),
                IN p_phone VARCHAR(50),
                IN p_email VARCHAR(255),
                IN p_qr_token VARCHAR(255),
                IN p_qr_image_path TEXT,
                IN p_initial_credits INT
            )
            BEGIN
                INSERT INTO members (
                    full_name,
                    phone,
                    email,
                    qr_token,
                    qr_image_path,
                    credits,
                    created_at
                )
                VALUES (
                    p_full_name,
                    p_phone,
                    p_email,
                    p_qr_token,
                    p_qr_image_path,
                    p_initial_credits,
                    DATE_FORMAT(NOW(), '%Y-%m-%dT%H:%i:%s')
                );

                SELECT LAST_INSERT_ID() AS member_id;
            END
            """
        )

        cursor.execute("DROP PROCEDURE IF EXISTS sp_add_credits")
        cursor.execute(
            """
            CREATE PROCEDURE sp_add_credits(
                IN p_member_id INT,
                IN p_amount INT,
                IN p_notes TEXT
            )
            BEGIN
                DECLARE v_exists INT DEFAULT 0;

                SELECT COUNT(*) INTO v_exists
                FROM members
                WHERE id = p_member_id;

                IF v_exists = 0 THEN
                    SIGNAL SQLSTATE '45000'
                    SET MESSAGE_TEXT = 'Member not found.';
                END IF;

                UPDATE members
                SET credits = credits + p_amount
                WHERE id = p_member_id;

                INSERT INTO credit_topups (
                    member_id,
                    amount,
                    notes,
                    created_at
                )
                VALUES (
                    p_member_id,
                    p_amount,
                    p_notes,
                    DATE_FORMAT(NOW(), '%Y-%m-%dT%H:%i:%s')
                );

                SELECT credits AS current_credits
                FROM members
                WHERE id = p_member_id;
            END
            """
        )

        cursor.execute("DROP PROCEDURE IF EXISTS sp_process_qr_scan")
        cursor.execute(
            """
            CREATE PROCEDURE sp_process_qr_scan(
                IN p_member_id INT
            )
            BEGIN
                DECLARE v_exists INT DEFAULT 0;
                DECLARE v_today VARCHAR(10);
                DECLARE v_name VARCHAR(255);
                DECLARE v_credits INT;
                DECLARE v_last_paid VARCHAR(10);
                DECLARE v_token VARCHAR(255);
                DECLARE v_new_credits INT;

                SET v_today = DATE_FORMAT(CURDATE(), '%Y-%m-%d');

                SELECT COUNT(*) INTO v_exists
                FROM members
                WHERE id = p_member_id;

                IF v_exists = 0 THEN
                    SELECT
                        'denied' AS status,
                        'Member not found.' AS message,
                        NULL AS member_id,
                        NULL AS full_name,
                        0 AS credits,
                        NULL AS qr_token;
                ELSE
                    SELECT
                        full_name,
                        credits,
                        COALESCE(last_paid_scan_date, ''),
                        qr_token
                    INTO
                        v_name,
                        v_credits,
                        v_last_paid,
                        v_token
                    FROM members
                    WHERE id = p_member_id
                    FOR UPDATE;

                    IF v_last_paid = v_today THEN
                        INSERT INTO attendance_logs (
                            member_id,
                            scan_token,
                            status,
                            credits_before,
                            credits_after,
                            notes,
                            created_at
                        )
                        VALUES (
                            p_member_id,
                            v_token,
                            'already_scanned',
                            v_credits,
                            v_credits,
                            'Already scanned today. No credit deducted.',
                            DATE_FORMAT(NOW(), '%Y-%m-%dT%H:%i:%s')
                        );

                        SELECT
                            'already_scanned' AS status,
                            'Already scanned today. No credit deducted.' AS message,
                            p_member_id AS member_id,
                            v_name AS full_name,
                            v_credits AS credits,
                            v_token AS qr_token;
                    ELSEIF v_credits <= 0 THEN
                        INSERT INTO attendance_logs (
                            member_id,
                            scan_token,
                            status,
                            credits_before,
                            credits_after,
                            notes,
                            created_at
                        )
                        VALUES (
                            p_member_id,
                            v_token,
                            'denied',
                            v_credits,
                            v_credits,
                            'No remaining credits.',
                            DATE_FORMAT(NOW(), '%Y-%m-%dT%H:%i:%s')
                        );

                        SELECT
                            'denied' AS status,
                            'No remaining credits.' AS message,
                            p_member_id AS member_id,
                            v_name AS full_name,
                            v_credits AS credits,
                            v_token AS qr_token;
                    ELSE
                        UPDATE members
                        SET
                            credits = credits - 1,
                            last_paid_scan_date = v_today
                        WHERE id = p_member_id;

                        SET v_new_credits = v_credits - 1;

                        INSERT INTO attendance_logs (
                            member_id,
                            scan_token,
                            status,
                            credits_before,
                            credits_after,
                            notes,
                            created_at
                        )
                        VALUES (
                            p_member_id,
                            v_token,
                            'approved',
                            v_credits,
                            v_new_credits,
                            'Credit deducted successfully.',
                            DATE_FORMAT(NOW(), '%Y-%m-%dT%H:%i:%s')
                        );

                        SELECT
                            'approved' AS status,
                            'Credit deducted successfully.' AS message,
                            p_member_id AS member_id,
                            v_name AS full_name,
                            v_new_credits AS credits,
                            v_token AS qr_token;
                    END IF;
                END IF;
            END
            """
        )

    def _create_mysql_event(self, cursor) -> None:
        cursor.execute("DROP EVENT IF EXISTS ev_daily_dashboard_summary")
        cursor.execute(
            """
            CREATE EVENT ev_daily_dashboard_summary
            ON SCHEDULE EVERY 1 DAY
            STARTS (CURRENT_DATE + INTERVAL 23 HOUR + INTERVAL 55 MINUTE)
            DO
                INSERT INTO daily_reports (
                    report_date,
                    total_members,
                    total_credits,
                    approved_entries,
                    topup_amount,
                    generated_at
                )
                SELECT
                    DATE_FORMAT(CURDATE(), '%Y-%m-%d'),
                    COUNT(*),
                    COALESCE(SUM(credits), 0),
                    (
                        SELECT COUNT(*)
                        FROM attendance_logs
                        WHERE status = 'approved'
                          AND LEFT(created_at, 10) = DATE_FORMAT(CURDATE(), '%Y-%m-%d')
                    ),
                    (
                        SELECT COALESCE(SUM(amount), 0)
                        FROM credit_topups
                        WHERE LEFT(created_at, 10) = DATE_FORMAT(CURDATE(), '%Y-%m-%d')
                    ),
                    DATE_FORMAT(NOW(), '%Y-%m-%dT%H:%i:%s')
                FROM members
                ON DUPLICATE KEY UPDATE
                    total_members = VALUES(total_members),
                    total_credits = VALUES(total_credits),
                    approved_entries = VALUES(approved_entries),
                    topup_amount = VALUES(topup_amount),
                    generated_at = VALUES(generated_at)
            """
        )

    def create_member(
        self,
        full_name: str,
        phone: str,
        email: str,
        qr_token: str,
        qr_image_path: str,
        initial_credits: int,
    ) -> int:
        if self.engine == "mysql":
            with self.connect() as connection:
                cursor = connection.cursor()
                cursor.execute(
                    "CALL sp_register_member(%s, %s, %s, %s, %s, %s)",
                    (full_name, phone, email, qr_token, qr_image_path, initial_credits),
                )
                row = self._fetch_first_result(cursor)
                return int(row["member_id"])

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

        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(sql, params)
            return cursor.lastrowid

    def get_members(self) -> list[dict]:
        sql = (
            "SELECT * FROM vw_member_credit_summary ORDER BY id DESC"
            if self.engine == "mysql"
            else "SELECT * FROM vw_member_credit_summary ORDER BY id DESC"
        )
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
        params = (member_id,)
        if self.engine == "mysql":
            sql = sql.replace("?", "%s")

        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(sql, params)
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_member_by_qr_token(self, token: str) -> dict | None:
        sql = "SELECT * FROM members WHERE qr_token = ?"
        params = (token,)
        if self.engine == "mysql":
            sql = sql.replace("?", "%s")

        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(sql, params)
            row = cursor.fetchone()
            return dict(row) if row else None

    def add_credits(self, member_id: int, amount: int) -> None:
        if self.engine == "mysql":
            with self.connect() as connection:
                cursor = connection.cursor()
                cursor.execute(
                    "CALL sp_add_credits(%s, %s, %s)",
                    (member_id, amount, "Manual top-up from desktop."),
                )
                self._drain_result_sets(cursor)
            return

        now = datetime.now().isoformat(timespec="seconds")
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute("UPDATE members SET credits = credits + ? WHERE id = ?", (amount, member_id))
            cursor.execute(
                """
                INSERT INTO credit_topups (member_id, amount, notes, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (member_id, amount, "Manual top-up from desktop.", now),
            )

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
        if self.engine == "mysql":
            with self.connect() as connection:
                cursor = connection.cursor()
                cursor.execute("CALL sp_process_qr_scan(%s)", (member_id,))
                row = self._fetch_first_result(cursor)

            if not row:
                return False, None, "Scan processing failed."

            member = None
            if row.get("member_id") is not None:
                member = self.get_member_by_id(int(row["member_id"]))

            success = str(row["status"]) in {"approved", "already_scanned"}
            return success, member, str(row["message"])

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
            cursor.execute(update_sql, (today, member_id, today))
            changed_rows = cursor.rowcount

            cursor.execute("SELECT * FROM members WHERE id = ?", (member_id,))
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
        if self.engine == "mysql":
            with self.connect() as connection:
                cursor = connection.cursor()
                cursor.execute("SELECT * FROM vw_dashboard_stats")
                row = dict(cursor.fetchone())
                return {
                    "total_members": int(row["total_members"]),
                    "total_credits": int(row["total_credits"]),
                    "low_credit_members": int(row["low_credit_members"]),
                    "today_entries": int(row["today_entries"]),
                    "today_topups": int(row["today_topups"]),
                    "saved_daily_reports": int(row["saved_daily_reports"]),
                }

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
        topups_sql = """
        SELECT COALESCE(SUM(amount), 0) AS today_topups
        FROM credit_topups
        WHERE created_at LIKE ?
        """
        reports_sql = "SELECT COUNT(*) AS saved_daily_reports FROM daily_reports"

        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(member_sql)
            total_members = int(dict(cursor.fetchone())["total_members"])

            cursor.execute(credits_sql)
            total_credits = int(dict(cursor.fetchone())["total_credits"])

            cursor.execute(low_credit_sql)
            low_credit_members = int(dict(cursor.fetchone())["low_credit_members"])

            cursor.execute(attendance_sql, (f"{day_prefix}%",))
            today_entries = int(dict(cursor.fetchone())["today_entries"])

            cursor.execute(topups_sql, (f"{day_prefix}%",))
            today_topups = int(dict(cursor.fetchone())["today_topups"])

            cursor.execute(reports_sql)
            saved_daily_reports = int(dict(cursor.fetchone())["saved_daily_reports"])

        return {
            "total_members": total_members,
            "total_credits": total_credits,
            "low_credit_members": low_credit_members,
            "today_entries": today_entries,
            "today_topups": today_topups,
            "saved_daily_reports": saved_daily_reports,
        }

    def get_attendance_logs(self) -> list[dict]:
        sql = "SELECT * FROM vw_transaction_history ORDER BY id DESC"
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(sql)
            return [dict(row) for row in cursor.fetchall()]

    def _fetch_first_result(self, cursor) -> dict | None:
        row = None
        if cursor.description:
            fetched = cursor.fetchone()
            row = dict(fetched) if fetched else None

        self._drain_result_sets(cursor)
        return row

    def _drain_result_sets(self, cursor) -> None:
        while cursor.nextset():
            if cursor.description:
                cursor.fetchall()
