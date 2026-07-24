<?php require 'bootstrap.php'; require 'partials.php';
$errors=[];
$allCauses=['Youth Services','Mental Health','Animal Welfare','Elderly Support','Poverty Relief','Disability Support','Education','Arts & Culture','Environment'];
if($_SERVER['REQUEST_METHOD']==='POST'){
 verify_csrf();
 $email=strtolower(trim($_POST['email']??'')); $password=$_POST['password']??''; $org=trim($_POST['organization']??''); $region=$_POST['region']??''; $causes=$_POST['causes']??[]; $turnover=$_POST['turnover']??'';
 $users=load_json('users.json');
 if(!filter_var($email,FILTER_VALIDATE_EMAIL)) $errors[]='Enter a valid email address.';
 if(strlen($password)<8) $errors[]='Password must contain at least 8 characters.';
 if(!$org||!$region||!$causes) $errors[]='Complete all required fields.';
 foreach($users as $u) if($u['email']===$email) $errors[]='An account already exists for this email.';
 if(!$errors){$id=count($users)?max(array_column($users,'id'))+1:1; $users[]=['id'=>$id,'organization'=>$org,'email'=>$email,'password_hash'=>password_hash($password,PASSWORD_DEFAULT),'region'=>$region,'causes'=>array_values($causes),'turnover'=>$turnover,'subscription_status'=>'Free','created_at'=>date('c')]; save_json('users.json',$users); $_SESSION['user_id']=$id; header('Location: subscribe.php'); exit;}
}
site_header('Create your account'); ?>
<section class="centered-page"><a class="page-back" href="index.php">← &nbsp; Back to home</a><div class="centered-intro"><h1>Create Your Account</h1><p>Join GrantSpotter to start finding the right funding for your organisation.</p></div><?php if($errors): ?><div class="alert error form-width"><?= e(implode(' ', $errors)) ?></div><?php endif; ?>
<form method="post" class="compact-form"><input type="hidden" name="csrf" value="<?= csrf_token() ?>"><label>Email Address<input type="email" name="email" placeholder="you@example.org" required value="<?= e($_POST['email']??'') ?>"></label><label>Password<div class="password-wrap"><input type="password" name="password" required minlength="8" value=""><span>◉</span></div></label><label>Organisation Name<input type="text" name="organization" placeholder="Your organisation name" required value="<?= e($_POST['organization']??'') ?>"></label><label>Geographic Region<select name="region" required><option value="">Select your region</option><?php foreach(['Yorkshire','North West','London','National'] as $r): ?><option <?= (($_POST['region']??'')===$r)?'selected':'' ?>><?= e($r) ?></option><?php endforeach; ?></select></label><fieldset><legend>Primary Cause <small>(Select all that apply)</small></legend><div class="chip-check-grid"><?php foreach($allCauses as $c): ?><label class="chip-check"><input type="checkbox" name="causes[]" value="<?= e($c) ?>" <?= in_array($c,$_POST['causes']??[],true)?'checked':'' ?>><span><?= e($c) ?></span></label><?php endforeach; ?></div></fieldset><label>Annual Turnover<select name="turnover"><option value="">Select annual turnover</option><option>Under £10k</option><option>£10k-£50k</option><option>£50k+</option></select></label><button class="btn btn-success full form-submit" type="submit">Create Account &amp; Continue <span>→</span></button><p class="form-legal">By creating an account you agree to our <a href="terms.php">Terms of Service</a><br>and <a href="privacy.php">Privacy Policy</a>.</p></form></section>
<?php site_footer(); ?>
