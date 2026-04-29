# XAMPP API

This PHP API lets the desktop app and the mobile app use the same XAMPP MySQL database.

## Setup

1. Copy this folder into your XAMPP `htdocs` directory.
2. Rename `config.example.php` to `config.php`.
3. Update the database settings in `config.php`.
4. Start Apache and MySQL in XAMPP.
5. Create the database in phpMyAdmin:

```sql
CREATE DATABASE gym_qr_system;
```

6. Open this in the browser to test:

```text
http://localhost/xampp_api/index.php?action=health
```

If it returns `{"ok":true}`, the API is working.

## Routes

- `GET index.php?action=health`
- `GET index.php?action=members`
- `GET index.php?action=logs`
- `GET index.php?action=stats`
- `POST index.php?action=create_member`
- `POST index.php?action=top_up`
- `POST index.php?action=scan`
