<?php
session_start();
$config = require __DIR__ . '/config.php';

define('DATA_DIR', __DIR__ . '/data');
define('UPLOAD_DIR', __DIR__ . '/uploads');

function load_json(string $file, array $fallback = []): array {
    $path = DATA_DIR . '/' . $file;
    if (!file_exists($path)) return $fallback;
    $decoded = json_decode((string)file_get_contents($path), true);
    return is_array($decoded) ? $decoded : $fallback;
}

function save_json(string $file, array $data): bool {
    if (!is_dir(DATA_DIR)) mkdir(DATA_DIR, 0755, true);
    return (bool)file_put_contents(DATA_DIR . '/' . $file, json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES), LOCK_EX);
}

function current_user(): ?array {
    if (empty($_SESSION['user_id'])) return null;
    foreach (load_json('users.json') as $user) {
        if ((int)$user['id'] === (int)$_SESSION['user_id']) return $user;
    }
    return null;
}

function update_user(array $updated): bool {
    $users = load_json('users.json');
    foreach ($users as $i => $user) {
        if ((int)$user['id'] === (int)$updated['id']) {
            $users[$i] = $updated;
            return save_json('users.json', $users);
        }
    }
    return false;
}

function require_login(): array {
    $user = current_user();
    if (!$user) {
        header('Location: login.php');
        exit;
    }
    return $user;
}

function require_active(): array {
    $user = require_login();
    if (($user['subscription_status'] ?? 'Free') !== 'Active') {
        header('Location: subscribe.php');
        exit;
    }
    return $user;
}

function e(?string $value): string {
    return htmlspecialchars((string)$value, ENT_QUOTES, 'UTF-8');
}

function csrf_token(): string {
    if (empty($_SESSION['csrf'])) $_SESSION['csrf'] = bin2hex(random_bytes(24));
    return $_SESSION['csrf'];
}

function verify_csrf(): void {
    if (!hash_equals($_SESSION['csrf'] ?? '', $_POST['csrf'] ?? '')) {
        http_response_code(419);
        exit('Session expired. Please go back and try again.');
    }
}

function days_remaining(string $deadline): int {
    $today = new DateTime('today');
    $end = new DateTime($deadline);
    return (int)$today->diff($end)->format('%r%a');
}

function matches_user(array $grant, array $user): bool {
    $regionMatch = in_array($user['region'] ?? '', $grant['regions'] ?? [], true) || in_array('National', $grant['regions'] ?? [], true);
    $userCauses = $user['causes'] ?? [];
    $causeMatch = count(array_intersect($userCauses, $grant['causes'] ?? [])) > 0;
    return $grant['status'] === 'Active' && $regionMatch && $causeMatch;
}
