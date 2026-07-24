<?php require 'bootstrap.php'; require 'partials.php'; $grants = array_slice(load_json('grants.json'),0,3); site_header('Find local grants faster'); ?>
<section class="hero visual-home">
  <div class="hero-copy">
    <h1>Stop wasting time<br>hunting for funding.<br><span>Get local grants matched<br>straight to your dashboard.</span></h1>
    <p>GrantSpotter helps small non-profits and community groups find local funding faster and easier.</p>
    <div class="hero-actions"><a class="btn btn-success" href="register.php">Find Funding <span>→</span></a></div>
  </div>
  <div class="hero-visual illustrated">
    <div class="leaf leaf-a"></div><div class="leaf leaf-b"></div><div class="leaf leaf-c"></div>
    <div class="illustration-base"></div>
    <div class="pouch-small"><span>£</span></div>
    <div class="magnifier"><span></span></div>
  </div>
</section>
<section class="testimonial-section" id="about">
  <h2>Trusted by community organisations across the UK</h2>
  <div class="testimonial-grid">
    <article><div class="trust-logo community-logo">✦ <span>COMMUNITY<br>FUND</span></div><blockquote>“GrantSpotter has saved us countless hours and helped us secure over £25k in funding.”</blockquote><small>— Youth Action North</small></article>
    <article><div class="trust-logo tudor-logo">the<br><strong>Tudor</strong>trust</div><blockquote>“An essential tool for grassroots organisations looking to make a real impact locally.”</blockquote><small>— The Tudor Trust</small></article>
    <article><div class="trust-logo henry-logo">The<br><strong>Henry Smith</strong><br>Charity</div><blockquote>“Connecting small charities with the right funding opportunities in their communities.”</blockquote><small>— Henry Smith Charity</small></article>
  </div>
</section>
<section class="latest-table-section" id="grants">
  <div class="table-heading"><h2>Latest Grants Added</h2><a href="register.php">View all grants →</a></div>
  <div class="public-grant-table">
  <?php foreach($grants as $g): ?><article class="public-grant-row"><div><strong><?= e($g['title']) ?></strong></div><div><?= e($g['funder']) ?></div><div class="table-amount">£<?= number_format($g['amount']) ?></div><div class="locked-copy"><span>♟</span> Create a free account to<br>unlock deadlines and links.</div></article><?php endforeach; ?>
  </div>
</section>
<?php site_footer(); ?>
