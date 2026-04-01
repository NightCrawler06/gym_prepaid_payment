# Gym QR Credit System

Gym prepaid credit and QR access system using Python, PyQt6, and a local database.

## Features

- Register gym members
- Generate a unique QR code for each member
- Add or top up credits
- Scan a QR code using the webcam
- Deduct one credit on the first valid scan of the day
- Mark repeat same-day scans as already scanned without deducting again
- Reject access when credits are empty
- View members and transaction logs
- Use SQLite by default, with optional MySQL/phpMyAdmin support

## Default database

The app uses SQLite out of the box, so you can run it immediately without setting up XAMPP or phpMyAdmin.

Database file:

`data/gym_system.db`

## Optional MySQL/phpMyAdmin setup

If you want to use a local MySQL database managed through phpMyAdmin, create a `db_config.json` file in the project root:

```json
{
  "engine": "mysql",
  "host": "127.0.0.1",
  "port": 3306,
  "user": "root",
  "password": "",
  "database": "gym_qr_system"
}
```

Then create the database in phpMyAdmin:

```sql
CREATE DATABASE gym_qr_system;
```

The app will create the required tables automatically on startup.

## Install

```powershell
cd C:\Users\USER\Documents\Playground
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```powershell
cd C:\Users\USER\Documents\Playground
python main.py
```

## Basic workflow

1. Register a new member.
2. The system generates a QR image automatically.
3. Add credits when needed.
4. In the Scan tab, start the camera and show the member QR to the webcam.
5. The first valid scan for the day deducts one credit.
6. If the same member is scanned again on the same day, the system marks it as already scanned and does not deduct again.

## Notes

- The app uses your default webcam for scanning.
- If another app is using the camera, close it first before starting the scanner.
- The interface includes dashboard cards, member management, and scan/payment feedback for front-desk use.
- If you want, the next version can add cashier accounts, printable receipts, and daily reports.
