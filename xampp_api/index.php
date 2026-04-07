<?php

require __DIR__ . '/helpers.php';
require __DIR__ . '/db.php';

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    json_response(['ok' => true]);
}

$action = $_GET['action'] ?? '';

try {
    $pdo = get_pdo();

    if ($action === 'health') {
        json_response(['ok' => true]);
    }

    if ($action === 'members' && $_SERVER['REQUEST_METHOD'] === 'GET') {
        $statement = $pdo->query("SELECT * FROM members ORDER BY id DESC");
        json_response(['members' => $statement->fetchAll()]);
    }

    if ($action === 'logs' && $_SERVER['REQUEST_METHOD'] === 'GET') {
        $statement = $pdo->query("
            SELECT
                attendance_logs.*,
                members.full_name
            FROM attendance_logs
            LEFT JOIN members ON members.id = attendance_logs.member_id
            ORDER BY attendance_logs.id DESC
        ");
        json_response(['logs' => $statement->fetchAll()]);
    }

    if ($action === 'stats' && $_SERVER['REQUEST_METHOD'] === 'GET') {
        $members = (int) $pdo->query("SELECT COUNT(*) FROM members")->fetchColumn();
        $credits = (int) $pdo->query("SELECT COALESCE(SUM(credits), 0) FROM members")->fetchColumn();
        $low_credit = (int) $pdo->query("SELECT COUNT(*) FROM members WHERE credits <= 2")->fetchColumn();

        $statement = $pdo->prepare("
            SELECT COUNT(*) FROM attendance_logs
            WHERE status = 'approved' AND created_at LIKE ?
        ");
        $statement->execute([today_prefix() . '%']);
        $today_paid_entries = (int) $statement->fetchColumn();

        json_response([
            'stats' => [
                'totalMembers' => $members,
                'totalCredits' => $credits,
                'todayPaidEntries' => $today_paid_entries,
                'lowCreditMembers' => $low_credit,
            ],
        ]);
    }

    if ($action === 'create_member' && $_SERVER['REQUEST_METHOD'] === 'POST') {
        $body = read_json_body();
        $full_name = trim($body['fullName'] ?? '');
        $phone = trim($body['phone'] ?? '');
        $email = trim($body['email'] ?? '');
        $initial_credits = (int) ($body['initialCredits'] ?? 0);

        if ($full_name === '') {
            json_response(['error' => 'Full name is required.'], 422);
        }

        $qr_token = build_token();
        $created_at = now_iso();
        $statement = $pdo->prepare("
            INSERT INTO members (full_name, phone, email, qr_token, qr_image_path, credits, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ");
        $statement->execute([
            $full_name,
            $phone,
            $email,
            $qr_token,
            '',
            $initial_credits,
            $created_at,
        ]);

        json_response([
            'member' => [
                'id' => (int) $pdo->lastInsertId(),
                'full_name' => $full_name,
                'phone' => $phone,
                'email' => $email,
                'qr_token' => $qr_token,
                'qr_image_path' => '',
                'credits' => $initial_credits,
                'created_at' => $created_at,
            ],
        ], 201);
    }

    if ($action === 'top_up' && $_SERVER['REQUEST_METHOD'] === 'POST') {
        $body = read_json_body();
        $member_id = (int) ($body['memberId'] ?? 0);
        $amount = (int) ($body['amount'] ?? 0);

        if ($member_id <= 0 || $amount <= 0) {
            json_response(['error' => 'Invalid member or amount.'], 422);
        }

        $statement = $pdo->prepare("UPDATE members SET credits = credits + ? WHERE id = ?");
        $statement->execute([$amount, $member_id]);
        json_response(['ok' => true]);
    }

    if ($action === 'scan' && $_SERVER['REQUEST_METHOD'] === 'POST') {
        $body = read_json_body();
        $scan_token = trim($body['scanToken'] ?? '');

        if ($scan_token === '') {
            json_response(['error' => 'Missing scan token.'], 422);
        }

        $pdo->beginTransaction();
        try {
            $statement = $pdo->prepare("SELECT * FROM members WHERE qr_token = ?");
            $statement->execute([$scan_token]);
            $member = $statement->fetch();

            if (!$member) {
                $log = $pdo->prepare("
                    INSERT INTO attendance_logs
                    (member_id, scan_token, status, credits_before, credits_after, notes, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ");
                $log->execute([null, $scan_token, 'denied', 0, 0, 'Unknown QR token.', now_iso()]);
                $pdo->commit();
                json_response([
                    'status' => 'denied',
                    'message' => 'Access denied. Unknown QR code.',
                ]);
            }

            $today = today_prefix();
            $credits_before = (int) $member['credits'];
            $update = $pdo->prepare("
                UPDATE members
                SET credits = credits - 1, last_paid_scan_date = ?
                WHERE id = ?
                  AND credits > 0
                  AND (last_paid_scan_date IS NULL OR last_paid_scan_date <> ?)
            ");
            $update->execute([$today, $member['id'], $today]);
            $changed_rows = $update->rowCount();

            $statement = $pdo->prepare("SELECT * FROM members WHERE id = ?");
            $statement->execute([$member['id']]);
            $current_member = $statement->fetch();

            $log = $pdo->prepare("
                INSERT INTO attendance_logs
                (member_id, scan_token, status, credits_before, credits_after, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ");

            if ($changed_rows === 1) {
                $log->execute([
                    $member['id'],
                    $scan_token,
                    'approved',
                    $credits_before,
                    (int) $current_member['credits'],
                    'Credit deducted successfully.',
                    now_iso(),
                ]);

                $pdo->commit();
                json_response([
                    'status' => 'approved',
                    'message' => 'Credit deducted successfully.',
                    'member' => $current_member,
                ]);
            }

            if (($current_member['last_paid_scan_date'] ?? null) === $today) {
                $current_credits = (int) $current_member['credits'];
                $log->execute([
                    $member['id'],
                    $scan_token,
                    'already_scanned',
                    $current_credits,
                    $current_credits,
                    'Already scanned today. No credit deducted.',
                    now_iso(),
                ]);

                $pdo->commit();
                json_response([
                    'status' => 'already_scanned',
                    'message' => 'Already scanned today. No credit deducted.',
                    'member' => $current_member,
                ]);
            }

            $current_credits = (int) $current_member['credits'];
            $log->execute([
                $member['id'],
                $scan_token,
                'denied',
                $current_credits,
                $current_credits,
                'No remaining credits.',
                now_iso(),
            ]);

            $pdo->commit();
            json_response([
                'status' => 'denied',
                'message' => 'Access denied. No remaining credits.',
                'member' => $current_member,
            ]);
        } catch (Throwable $transaction_error) {
            if ($pdo->inTransaction()) {
                $pdo->rollBack();
            }
            throw $transaction_error;
        }
    }

    json_response(['error' => 'Route not found.'], 404);
} catch (Throwable $error) {
    json_response([
        'error' => $error->getMessage(),
    ], 500);
}
