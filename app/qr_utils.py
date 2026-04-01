from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import cv2
import qrcode

from .config import QR_DIR, ensure_directories


def generate_member_qr(full_name: str) -> tuple[str, str]:
    ensure_directories()
    slug = "_".join(full_name.lower().split())[:30] or "member"
    token = str(uuid4())
    file_path = QR_DIR / f"{slug}_{token[:8]}.png"

    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(token)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    image.save(file_path)

    return token, str(file_path)


def decode_qr_from_image(image_path: str) -> str | None:
    path = Path(image_path)
    if not path.exists():
        return None

    image = cv2.imread(str(path))
    if image is None:
        return None

    detector = cv2.QRCodeDetector()
    data, _, _ = detector.detectAndDecode(image)
    return data or None


def decode_qr_from_frame(frame) -> str | None:
    detector = cv2.QRCodeDetector()
    data, _, _ = detector.detectAndDecode(frame)
    return data or None
