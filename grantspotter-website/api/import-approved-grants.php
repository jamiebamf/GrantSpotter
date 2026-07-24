<?php
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');

// IMPORTANT: Set the same secret in the crawler's WEBSITE_IMPORT_SECRET setting.
const IMPORT_SECRET = 'REPLACE_WITH_A_LONG_RANDOM_SECRET';

$provided = $_SERVER['HTTP_X_GRANTSPOTTER_SECRET'] ?? '';
if (!hash_equals(IMPORT_SECRET, $provided)) {
    http_response_code(401);
    echo json_encode(['ok' => false, 'error' => 'Unauthorised']);
    exit;
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['ok' => false, 'error' => 'POST required']);
    exit;
}

$payload = json_decode((string)file_get_contents('php://input'), true);
if (!is_array($payload)) {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => 'Invalid JSON']);
    exit;
}

$required = ['title', 'funder', 'url', 'external_id'];
foreach ($required as $field) {
    if (empty($payload[$field])) {
        http_response_code(422);
        echo json_encode(['ok' => false, 'error' => "Missing field: {$field}"]);
        exit;
    }
}

$dataDir = dirname(__DIR__) . '/data';
$file = $dataDir . '/grants.json';
if (!is_dir($dataDir)) mkdir($dataDir, 0755, true);
$grants = file_exists($file) ? json_decode((string)file_get_contents($file), true) : [];
if (!is_array($grants)) $grants = [];

$record = [
    'id' => 0,
    'external_id' => (string)$payload['external_id'],
    'title' => trim((string)$payload['title']),
    'funder' => trim((string)$payload['funder']),
    'amount' => max(0, (float)($payload['amount'] ?? 0)),
    'regions' => array_values(array_filter((array)($payload['regions'] ?? ['National']), 'is_string')),
    'causes' => array_values(array_filter((array)($payload['causes'] ?? ['Community Development']), 'is_string')),
    'deadline' => $payload['deadline'] ?: date('Y-m-d', strtotime('+1 year')),
    'deadline_type' => (string)($payload['deadline_type'] ?? 'unknown'),
    'url' => filter_var((string)$payload['url'], FILTER_VALIDATE_URL) ?: '',
    'source_url' => filter_var((string)($payload['source_url'] ?? ''), FILTER_VALIDATE_URL) ?: '',
    'status' => 'Active',
    'summary' => trim((string)($payload['summary'] ?? '')),
    'verified_at' => (string)($payload['verified_at'] ?? date(DATE_ATOM)),
];

$found = false;
foreach ($grants as $index => $existing) {
    if (($existing['external_id'] ?? '') === $record['external_id']) {
        $record['id'] = (int)($existing['id'] ?? 0);
        $grants[$index] = array_merge($existing, $record);
        $found = true;
        break;
    }
}
if (!$found) {
    $ids = array_map(fn($g) => (int)($g['id'] ?? 0), $grants);
    $record['id'] = ($ids ? max($ids) : 0) + 1;
    $grants[] = $record;
}

$temp = $file . '.tmp';
$json = json_encode($grants, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
if ($json === false || file_put_contents($temp, $json, LOCK_EX) === false || !rename($temp, $file)) {
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => 'Could not save grant data']);
    exit;
}

echo json_encode(['ok' => true, 'action' => $found ? 'updated' : 'created', 'id' => $record['id']]);
