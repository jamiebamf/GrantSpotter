<?php
function site_header(string $title, bool $dashboard = false): void {
    global $config;
    $user = current_user();
    ?>
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title><?= e($title) ?> | <?= e($config['site_name']) ?></title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="assets/css/style.css"></head><body>
<?php if (!$dashboard): ?>
<header class="topbar"><a class="brand" href="index.php"><span class="brand-mark"><span class="brand-lens"></span></span><span>GrantSpotter</span></a><nav><a href="index.php#about">About</a><?php if($user): ?><a class="btn btn-primary nav-button" href="dashboard.php">Dashboard</a><?php else: ?><a class="btn btn-primary nav-button" href="login.php">Login</a><?php endif; ?></nav></header>
<?php endif; ?>
<?php
}

function site_footer(): void { ?>
<footer class="footer"><div><a class="brand brand-light" href="index.php"><span class="brand-mark"><span class="brand-lens"></span></span><span>GrantSpotter</span></a><p>Local funding opportunities, matched simply.</p></div><div><p>© <?= date('Y') ?> GrantSpotter</p><a href="privacy.php">Privacy</a> · <a href="terms.php">Terms</a></div></footer>
<script src="assets/js/app.js"></script></body></html>
<?php }

function dashboard_start(array $user, string $active): void { site_header(ucwords(str_replace('_',' ',$active)), true); ?>
<div class="app-shell"><aside class="sidebar"><a class="brand brand-light" href="dashboard.php"><span class="brand-mark"><span class="brand-lens"></span></span><span>GrantSpotter</span></a>
<nav class="side-nav"><a class="<?= $active==='matches'?'active':'' ?>" href="dashboard.php"><span class="nav-icon">◎</span><span>My Matches</span></a><a class="<?= $active==='vault'?'active':'' ?>" href="vault.php"><span class="nav-icon">■</span><span>Document Vault</span></a><a class="<?= $active==='subscription'?'active':'' ?>" href="subscription.php"><span class="nav-icon">⚙</span><span>Subscription</span></a><a class="<?= $active==='profile'?'active':'' ?>" href="profile.php"><span class="nav-icon">♙</span><span>My Profile</span></a></nav>
<a class="logout" href="logout.php"><span class="nav-icon">↪</span><span>Logout</span></a></aside><main class="workspace">
<header class="mobile-app-header"><a class="brand" href="dashboard.php"><span class="brand-mark"><span class="brand-lens"></span></span><span>GrantSpotter</span></a><button class="menu-toggle" aria-label="Open menu">☰</button></header>
<?php }
function dashboard_end(): void { ?></main></div><script src="assets/js/app.js"></script></body></html><?php }
