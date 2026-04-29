from __future__ import annotations

import os
import sys
from datetime import datetime

import cv2

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .database import Database
from .mailer import send_member_qr_email
from .qr_utils import decode_qr_from_frame, generate_member_qr


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.db = Database()
        self.selected_member_id: int | None = None
        self.camera: cv2.VideoCapture | None = None
        self.camera_timer = QTimer(self)
        self.camera_timer.timeout.connect(self.update_camera_frame)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_all_data)
        self.last_scanned_token: str | None = None
        self.scan_cooldown_ticks = 0
        self.last_scan_summary = "Scanner ready."
        self.last_registered_member: dict | None = None

        self.setWindowTitle("Gym QR Credit System")
        self.resize(1380, 860)
        self._build_ui()
        self._apply_styles()
        self.refresh_all_data()
        self.refresh_timer.start(5000)

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        header = self._build_header()
        stats = self._build_stats_row()

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_register_tab(), "Registration")
        self.tabs.addTab(self._build_members_tab(), "Members")
        self.tabs.addTab(self._build_scan_tab(), "Scanner")
        self.tabs.addTab(self._build_logs_tab(), "Transactions")

        root.addWidget(header)
        root.addLayout(stats)
        root.addWidget(self.tabs)
        self.setCentralWidget(central)

    def _build_header(self) -> QFrame:
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(20, 18, 20, 18)

        title_box = QVBoxLayout()
        title = QLabel("Gym QR Credit System")
        title.setObjectName("AppTitle")
        subtitle = QLabel(
            "Member registration, credit management, and QR access scanning."
        )
        subtitle.setObjectName("AppSubtitle")
        subtitle.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        self.clock_label = QLabel("")
        self.clock_label.setObjectName("ClockLabel")
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        layout.addLayout(title_box, 1)
        layout.addWidget(self.clock_label)
        self._update_clock()
        return frame

    def _build_stats_row(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(12)
        top_row = QHBoxLayout()
        bottom_row = QHBoxLayout()
        top_row.setSpacing(12)
        bottom_row.setSpacing(12)

        self.total_members_card = self._create_stat_card("Total Members", "0")
        self.total_credits_card = self._create_stat_card("Total Credits", "0")
        self.today_entries_card = self._create_stat_card("Today's Paid Entries", "0")
        self.low_credit_card = self._create_stat_card("Low Credit Alerts", "0")
        self.today_topups_card = self._create_stat_card("Today's Top-Ups", "0")
        self.saved_reports_card = self._create_stat_card("Saved Daily Reports", "0")

        top_row.addWidget(self.total_members_card)
        top_row.addWidget(self.total_credits_card)
        top_row.addWidget(self.today_entries_card)
        bottom_row.addWidget(self.low_credit_card)
        bottom_row.addWidget(self.today_topups_card)
        bottom_row.addWidget(self.saved_reports_card)

        layout.addLayout(top_row)
        layout.addLayout(bottom_row)
        return layout

    def _create_stat_card(self, title: str, value: str) -> QFrame:
        card = QFrame()
        card.setObjectName("StatCard")
        content = QVBoxLayout(card)
        content.setContentsMargins(16, 14, 16, 14)
        label = QLabel(title)
        label.setObjectName("StatTitle")
        number = QLabel(value)
        number.setObjectName("StatValue")
        card.title_label = label
        card.value_label = number
        content.addWidget(label)
        content.addWidget(number)
        return card

    def _build_register_tab(self) -> QWidget:
        tab = QWidget()
        root = QHBoxLayout(tab)
        root.setSpacing(16)

        form_box = QGroupBox("New Member")
        form_layout = QFormLayout(form_box)
        form_layout.setSpacing(14)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Juan Dela Cruz")
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("09XXXXXXXXX")
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("member@email.com")
        self.initial_credits_input = QSpinBox()
        self.initial_credits_input.setRange(0, 100000)
        self.initial_credits_input.setValue(5)

        self.register_button = QPushButton("Register Member")
        self.register_button.clicked.connect(self.register_member)
        self.email_qr_button = QPushButton("Email QR to Member")
        self.email_qr_button.clicked.connect(self.email_latest_qr)
        self.email_qr_button.setEnabled(False)

        form_layout.addRow("Full Name", self.name_input)
        form_layout.addRow("Phone", self.phone_input)
        form_layout.addRow("Email", self.email_input)
        form_layout.addRow("Initial Credits", self.initial_credits_input)
        form_layout.addRow(self.register_button)
        form_layout.addRow(self.email_qr_button)

        preview_box = QGroupBox("Generated QR")
        preview_layout = QVBoxLayout(preview_box)
        self.qr_preview_label = QLabel("No QR generated yet.")
        self.qr_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_preview_label.setMinimumHeight(320)
        self.qr_preview_label.setObjectName("PreviewSurface")
        self.qr_path_label = QLabel("")
        self.qr_path_label.setWordWrap(True)
        self.qr_path_label.setObjectName("MutedLabel")
        preview_layout.addWidget(self.qr_preview_label)
        preview_layout.addWidget(self.qr_path_label)

        root.addWidget(form_box, 1)
        root.addWidget(preview_box, 1)
        return tab

    def _build_members_tab(self) -> QWidget:
        tab = QWidget()
        root = QVBoxLayout(tab)
        root.setSpacing(14)

        top_panel = QFrame()
        top_panel.setObjectName("Panel")
        top_panel_layout = QHBoxLayout(top_panel)
        top_panel_layout.setContentsMargins(16, 14, 16, 14)

        self.members_table = QTableWidget(0, 8)
        self.members_table.setHorizontalHeaderLabels(
            ["ID", "Name", "Phone", "Email", "Credits", "QR Token", "QR Image", "Created"]
        )
        self.members_table.cellClicked.connect(self.on_member_selected)
        self.members_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.members_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.members_table.verticalHeader().setVisible(False)
        self.members_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.members_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.members_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        self.selected_member_label = QLabel("Selected Member: none")
        self.selected_member_label.setObjectName("SelectedLabel")
        self.top_up_input = QSpinBox()
        self.top_up_input.setRange(1, 100000)
        self.top_up_input.setValue(5)
        self.top_up_button = QPushButton("Add Credits")
        self.top_up_button.clicked.connect(self.top_up_member)
        self.refresh_members_button = QPushButton("Refresh")
        self.refresh_members_button.clicked.connect(self.refresh_members_table)

        top_up_caption = QLabel("Top Up Credits")
        top_up_caption.setObjectName("MutedLabel")
        top_panel_layout.addWidget(self.selected_member_label, 1)
        top_panel_layout.addWidget(top_up_caption)
        top_panel_layout.addWidget(self.top_up_input)
        top_panel_layout.addWidget(self.top_up_button)
        top_panel_layout.addWidget(self.refresh_members_button)

        root.addWidget(top_panel)
        root.addWidget(self.members_table)
        return tab

    def _build_scan_tab(self) -> QWidget:
        tab = QWidget()
        root = QHBoxLayout(tab)
        root.setSpacing(16)

        left_column = QVBoxLayout()
        right_column = QVBoxLayout()

        info = QLabel(
            "Use the webcam to scan a member QR. The first scan for the day deducts one credit. Additional same-day scans show as already scanned and do not deduct again."
        )
        info.setWordWrap(True)
        info.setObjectName("MutedLabel")

        actions = QHBoxLayout()
        self.camera_status_label = QLabel("Camera stopped.")
        self.camera_status_label.setObjectName("StatusPill")
        self.start_camera_button = QPushButton("Start Camera")
        self.start_camera_button.clicked.connect(self.start_camera)
        self.stop_camera_button = QPushButton("Stop Camera")
        self.stop_camera_button.clicked.connect(self.stop_camera)
        actions.addWidget(self.camera_status_label, 1)
        actions.addWidget(self.start_camera_button)
        actions.addWidget(self.stop_camera_button)

        camera_box = QGroupBox("Camera Preview")
        camera_layout = QVBoxLayout(camera_box)
        self.camera_preview_label = QLabel("Camera preview will appear here.")
        self.camera_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_preview_label.setMinimumHeight(420)
        self.camera_preview_label.setObjectName("CameraSurface")
        camera_layout.addWidget(self.camera_preview_label)

        result_box = QGroupBox("Payment Result")
        result_layout = QVBoxLayout(result_box)
        self.scan_result_label = QLabel("Waiting for scan.")
        self.scan_result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scan_result_label.setMinimumHeight(220)
        self.scan_result_label.setObjectName("ResultSurface")
        result_layout.addWidget(self.scan_result_label)

        queue_box = QGroupBox("Scanner Info")
        queue_layout = QVBoxLayout(queue_box)
        self.scan_hint_label = QLabel(
            "Position the QR code in front of the camera. The system will process the scan automatically."
        )
        self.scan_hint_label.setWordWrap(True)
        self.scan_hint_label.setObjectName("MutedLabel")
        self.last_scan_label = QLabel(f"Latest Event: {self.last_scan_summary}")
        self.last_scan_label.setWordWrap(True)
        self.last_scan_label.setObjectName("SelectedLabel")
        queue_layout.addWidget(self.scan_hint_label)
        queue_layout.addWidget(self.last_scan_label)

        left_column.addWidget(info)
        left_column.addLayout(actions)
        left_column.addWidget(camera_box, 1)
        right_column.addWidget(result_box)
        right_column.addWidget(queue_box)
        right_column.addStretch(1)

        root.addLayout(left_column, 2)
        root.addLayout(right_column, 1)
        return tab

    def _build_logs_tab(self) -> QWidget:
        tab = QWidget()
        root = QVBoxLayout(tab)
        root.setSpacing(14)

        panel = QFrame()
        panel.setObjectName("Panel")
        panel_layout = QHBoxLayout(panel)
        panel_layout.setContentsMargins(16, 14, 16, 14)
        log_caption = QLabel("Credit and Scan History")
        log_caption.setObjectName("SelectedLabel")
        log_help = QLabel("Includes credit deductions, already scanned records, denied scans, and scan details.")
        log_help.setObjectName("MutedLabel")
        log_help.setWordWrap(True)
        panel_text = QVBoxLayout()
        panel_text.addWidget(log_caption)
        panel_text.addWidget(log_help)

        self.refresh_logs_button = QPushButton("Refresh Logs")
        self.refresh_logs_button.clicked.connect(self.refresh_logs_table)

        panel_layout.addLayout(panel_text, 1)
        panel_layout.addWidget(self.refresh_logs_button)

        self.logs_table = QTableWidget(0, 8)
        self.logs_table.setHorizontalHeaderLabels(
            ["ID", "Member", "Status", "Credits Before", "Credits After", "Notes", "Created At", "Token"]
        )
        self.logs_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.logs_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.logs_table.verticalHeader().setVisible(False)
        self.logs_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.logs_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.logs_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.logs_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.logs_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        root.addWidget(panel)
        root.addWidget(self.logs_table)
        return tab

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background: #f3f4f6;
                color: #1f2937;
                font-family: "Segoe UI";
                font-size: 13px;
            }
            QTabWidget::pane {
                background: #ffffff;
                border: 1px solid #d1d5db;
                border-radius: 10px;
            }
            QGroupBox {
                background: #ffffff;
                border: 1px solid #d1d5db;
                border-radius: 10px;
                font-weight: 600;
                margin-top: 10px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: #374151;
            }
            QLineEdit, QSpinBox, QTableWidget {
                background: #ffffff;
                border: 1px solid #d1d5db;
                border-radius: 8px;
                padding: 8px 10px;
            }
            QLabel {
                background: transparent;
                border: none;
            }
            QLineEdit:focus, QSpinBox:focus {
                border: 1px solid #2563eb;
            }
            QPushButton {
                background: #2563eb;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 16px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #1d4ed8;
            }
            QPushButton:pressed {
                background: #1e40af;
            }
            QTabBar::tab {
                background: #e5e7eb;
                color: #374151;
                padding: 10px 16px;
                margin-right: 6px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                font-weight: 600;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                color: #2563eb;
            }
            QHeaderView::section {
                background: #f3f4f6;
                color: #374151;
                padding: 9px;
                border: none;
                border-bottom: 1px solid #d1d5db;
                font-weight: 600;
            }
            QTableWidget {
                gridline-color: #e5e7eb;
                selection-background-color: #dbeafe;
                selection-color: #1f2937;
            }
            QLabel#AppTitle {
                font-size: 24px;
                font-weight: 700;
                color: #111827;
            }
            QLabel#AppSubtitle {
                color: #6b7280;
                font-size: 13px;
            }
            QLabel#ClockLabel {
                background: #f3f4f6;
                color: #111827;
                border: 1px solid #d1d5db;
                border-radius: 8px;
                padding: 10px 14px;
                font-size: 13px;
                font-weight: 600;
                min-width: 220px;
            }
            QFrame#StatCard {
                background: #ffffff;
                border: 1px solid #d1d5db;
                border-radius: 10px;
            }
            QLabel#StatTitle {
                color: #6b7280;
                font-size: 12px;
                font-weight: 600;
            }
            QLabel#StatValue {
                color: #111827;
                font-size: 24px;
                font-weight: 700;
            }
            QLabel#PreviewSurface, QLabel#CameraSurface, QLabel#ResultSurface {
                background: #f9fafb;
                border: 1px solid #d1d5db;
                border-radius: 10px;
                padding: 16px;
            }
            QLabel#CameraSurface {
                background: #111827;
                color: #e5e7eb;
            }
            QLabel#ResultSurface {
                font-size: 18px;
                font-weight: 700;
                color: #111827;
            }
            QLabel#MutedLabel {
                color: #6b7280;
            }
            QLabel#SelectedLabel {
                color: #1f2937;
                font-weight: 600;
            }
            QLabel#StatusPill {
                background: #f3f4f6;
                color: #374151;
                border: 1px solid #d1d5db;
                border-radius: 8px;
                padding: 8px 12px;
                font-weight: 600;
            }
            QFrame#Panel {
                background: #ffffff;
                border: 1px solid #d1d5db;
                border-radius: 10px;
            }
            QFrame {
                background: transparent;
                border: none;
            }
            """
        )

    def _update_clock(self) -> None:
        now = datetime.now().strftime("%B %d, %Y  %I:%M %p")
        self.clock_label.setText(f"Desk Time\n{now}")

    def refresh_dashboard(self) -> None:
        self._show_loading("Loading dashboard...")
        stats = self.db.get_dashboard_stats()
        self.total_members_card.value_label.setText(str(stats["total_members"]))
        self.total_credits_card.value_label.setText(str(stats["total_credits"]))
        self.today_entries_card.value_label.setText(str(stats["today_entries"]))
        self.low_credit_card.value_label.setText(str(stats["low_credit_members"]))
        self.today_topups_card.value_label.setText(str(stats["today_topups"]))
        self.saved_reports_card.value_label.setText(str(stats["saved_daily_reports"]))
        self._update_clock()
        self._show_ready()

    def refresh_all_data(self) -> None:
        self.refresh_dashboard()
        self.refresh_members_table()
        self.refresh_logs_table()

    def register_member(self) -> None:
        full_name = self.name_input.text().strip()
        phone = self.phone_input.text().strip()
        email = self.email_input.text().strip()
        initial_credits = int(self.initial_credits_input.value())

        if not full_name:
            QMessageBox.warning(self, "Missing Name", "Please enter the member's full name.")
            return

        token, qr_path = generate_member_qr(full_name)
        member_id = self.db.create_member(
            full_name=full_name,
            phone=phone,
            email=email,
            qr_token=token,
            qr_image_path=qr_path,
            initial_credits=initial_credits,
        )

        self._show_qr_preview(qr_path)
        self.qr_path_label.setText(f"Saved QR: {qr_path}\nMember ID: {member_id}\nToken: {token}")
        self.last_registered_member = {
            "full_name": full_name,
            "email": email,
            "qr_path": qr_path,
            "token": token,
        }
        self.email_qr_button.setEnabled(True)

        self.name_input.clear()
        self.phone_input.clear()
        self.email_input.clear()
        self.initial_credits_input.setValue(5)

        self.refresh_all_data()
        QMessageBox.information(self, "Success", "Member registered and QR generated successfully.")

    def email_latest_qr(self) -> None:
        if not self.last_registered_member:
            QMessageBox.warning(self, "No QR", "Register a member first.")
            return

        email = self.last_registered_member["email"]
        if not email:
            QMessageBox.warning(self, "Missing Email", "This member has no email address.")
            return

        self._show_loading("Sending QR email...")
        QApplication.processEvents()
        ok, message = send_member_qr_email(
            recipient_email=email,
            member_name=self.last_registered_member["full_name"],
            qr_image_path=self.last_registered_member["qr_path"],
            qr_token=self.last_registered_member["token"],
        )
        self._show_ready()

        if ok:
            QMessageBox.information(self, "Email Sent", message)
        else:
            QMessageBox.warning(self, "Email Not Sent", message)

    def _show_qr_preview(self, qr_path: str) -> None:
        pixmap = QPixmap(qr_path)
        scaled = pixmap.scaled(
            300,
            300,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.qr_preview_label.setPixmap(scaled)
        self.qr_preview_label.setText("")

    def refresh_members_table(self) -> None:
        self._show_loading("Loading members...")
        members = self.db.get_members()
        self.members_table.setRowCount(len(members))

        for row_index, member in enumerate(members):
            values = [
                member["id"],
                member["full_name"],
                member["phone"] or "",
                member["email"] or "",
                member["credits"],
                member["qr_token"],
                member["qr_image_path"],
                member["created_at"],
            ]
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column_index == 4 and int(member["credits"]) <= 2:
                    item.setForeground(QColor("#c1121f"))
                    item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                self.members_table.setItem(row_index, column_index, item)
        self._show_ready()

    def on_member_selected(self, row: int, _: int) -> None:
        member_id_item = self.members_table.item(row, 0)
        member_name_item = self.members_table.item(row, 1)
        if not member_id_item or not member_name_item:
            return

        self.selected_member_id = int(member_id_item.text())
        self.selected_member_label.setText(
            f"Selected Member: {member_name_item.text()} (ID {self.selected_member_id})"
        )

    def top_up_member(self) -> None:
        if self.selected_member_id is None:
            QMessageBox.warning(self, "No Selection", "Please select a member first.")
            return

        if not self._confirm_top_up_access():
            return

        amount = int(self.top_up_input.value())
        self.db.add_credits(self.selected_member_id, amount)
        self.refresh_all_data()
        QMessageBox.information(self, "Success", f"{amount} credit(s) added successfully.")

    def _confirm_top_up_access(self) -> bool:
        admin_pin = os.getenv("GYM_ADMIN_PIN", "1234")
        pin, ok = QInputDialog.getText(
            self,
            "Top Up Authorization",
            "Enter admin PIN:",
            QLineEdit.EchoMode.Password,
        )

        if not ok:
            return False

        if pin != admin_pin:
            QMessageBox.warning(self, "Invalid PIN", "Credit top-up was not authorized.")
            return False

        return True

    def start_camera(self) -> None:
        if self.camera and self.camera.isOpened():
            return

        self.camera = cv2.VideoCapture(0)
        if not self.camera.isOpened():
            self.camera = None
            self.camera_status_label.setText("Camera unavailable.")
            QMessageBox.warning(self, "Camera Error", "Unable to open the webcam.")
            return

        self.camera_timer.start(30)
        self.camera_status_label.setText("Camera running.")
        self._set_result_state("Waiting for scan.", "#102a43", "#f9fbfd")

    def stop_camera(self) -> None:
        self.camera_timer.stop()
        if self.camera:
            self.camera.release()
            self.camera = None
        self.camera_preview_label.setPixmap(QPixmap())
        self.camera_preview_label.setText("Camera preview will appear here.")
        self.camera_status_label.setText("Camera stopped.")

    def update_camera_frame(self) -> None:
        if not self.camera:
            return

        ok, frame = self.camera.read()
        if not ok:
            self.camera_status_label.setText("Camera read failed.")
            return

        self._set_camera_preview(frame)

        if self.scan_cooldown_ticks > 0:
            self.scan_cooldown_ticks -= 1
            return

        token = decode_qr_from_frame(frame)
        if not token:
            self.last_scanned_token = None
            return

        if token == self.last_scanned_token:
            return

        self.last_scanned_token = token
        self.scan_cooldown_ticks = 30
        self.process_detected_token(token)

    def _set_camera_preview(self, frame) -> None:
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, channels = rgb_frame.shape
        bytes_per_line = channels * width
        image = QImage(
            rgb_frame.data,
            width,
            height,
            bytes_per_line,
            QImage.Format.Format_RGB888,
        )
        pixmap = QPixmap.fromImage(image).scaled(
            820,
            460,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.camera_preview_label.setPixmap(pixmap)
        self.camera_preview_label.setText("")

    def _set_result_state(self, text: str, text_color: str, background_color: str) -> None:
        self.scan_result_label.setText(text)
        self.scan_result_label.setStyleSheet(
            f"""
            background: {background_color};
            color: {text_color};
            border: 1px solid #b7c9dc;
            border-radius: 14px;
            padding: 18px;
            font-size: 18px;
            font-weight: 700;
            """
        )

    def process_detected_token(self, token: str) -> None:
        member = self.db.get_member_by_qr_token(token)
        if not member:
            self.db.log_attendance(
                member_id=None,
                scan_token=token,
                status="denied",
                credits_before=0,
                credits_after=0,
                notes="Unknown QR token.",
            )
            self.last_scan_summary = f"Unknown QR scanned at {datetime.now().strftime('%I:%M %p')}."
            self.last_scan_label.setText(f"Latest Event: {self.last_scan_summary}")
            self.refresh_all_data()
            self._set_result_state("Access denied.\nUnknown member QR.", "#9d0208", "#fff1f1")
            return

        success, updated_member, message = self.db.consume_credit_for_check_in(member["id"])
        self.refresh_all_data()

        if success and updated_member:
            self.last_scan_summary = (
                f"{updated_member['full_name']} processed at {datetime.now().strftime('%I:%M %p')}."
            )
            self.last_scan_label.setText(f"Latest Event: {self.last_scan_summary}")
            if "Already scanned today" in message:
                self._set_result_state(
                    f"Already scanned today.\nMember: {updated_member['full_name']}\nRemaining credits: {updated_member['credits']}",
                    "#9c6644",
                    "#fff7ed",
                )
            else:
                self._set_result_state(
                    f"Access approved.\nMember: {updated_member['full_name']}\nRemaining credits: {updated_member['credits']}",
                    "#166534",
                    "#effaf3",
                )
        else:
            self.last_scan_summary = f"{member['full_name']} denied at {datetime.now().strftime('%I:%M %p')}."
            self.last_scan_label.setText(f"Latest Event: {self.last_scan_summary}")
            self._set_result_state(
                f"Access denied.\nMember: {member['full_name']}\nReason: {message}",
                "#9d0208",
                "#fff1f1",
            )

    def refresh_logs_table(self) -> None:
        self._show_loading("Loading transactions...")
        logs = self.db.get_attendance_logs()
        self.logs_table.setRowCount(len(logs))

        for row_index, log in enumerate(logs):
            values = [
                log["id"],
                log.get("full_name") or "Unknown",
                log["status"],
                log["credits_before"],
                log["credits_after"],
                log["notes"] or "",
                log["created_at"],
                log["scan_token"],
            ]
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column_index == 2:
                    status = str(value)
                    if status == "approved":
                        item.setForeground(QColor("#166534"))
                    elif status == "already_scanned":
                        item.setForeground(QColor("#9c6644"))
                    elif status == "denied":
                        item.setForeground(QColor("#9d0208"))
                    item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                self.logs_table.setItem(row_index, column_index, item)
        self._show_ready()

    def _show_loading(self, message: str) -> None:
        self.statusBar().showMessage(message)
        QApplication.processEvents()

    def _show_ready(self) -> None:
        self.statusBar().showMessage("Ready", 2500)

    def closeEvent(self, event) -> None:
        self.stop_camera()
        super().closeEvent(event)


def run() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
