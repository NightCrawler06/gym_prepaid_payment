<?php

function get_pdo(): PDO
{
    static $pdo = null;

    if ($pdo instanceof PDO) {
        return $pdo;
    }

    $config_path = __DIR__ . DIRECTORY_SEPARATOR . 'config.php';
    if (!file_exists($config_path)) {
        http_response_code(500);
        echo json_encode([
            'error' => 'Missing config.php. Copy config.example.php to config.php and update it.',
        ]);
        exit;
    }

    $config = require $config_path;
    $dsn = sprintf(
        'mysql:host=%s;port=%d;dbname=%s;charset=utf8mb4',
        $config['host'],
        $config['port'],
        $config['database']
    );

    $pdo = new PDO(
        $dsn,
        $config['user'],
        $config['password'],
        [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        ]
    );

    initialize_schema($pdo);
    return $pdo;
}

function initialize_schema(PDO $pdo): void
{
    $pdo->exec("
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
    ");

    $pdo->exec("
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
    ");

    $column = $pdo->query("SHOW COLUMNS FROM members LIKE 'last_paid_scan_date'")->fetch();
    if (!$column) {
        $pdo->exec("ALTER TABLE members ADD COLUMN last_paid_scan_date VARCHAR(10) NULL");
    }
}
