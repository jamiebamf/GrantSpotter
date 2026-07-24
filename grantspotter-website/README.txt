GRANTSPOTTER - READY-TO-UPLOAD PHP BUILD

1. Upload all files and folders to your hosting public_html directory.
2. Make sure the data and uploads folders are writable by PHP (usually 0755; some hosts require 0775).
3. Open config.php and replace the two Stripe checkout URLs.
4. Register an account. Until Stripe is connected, use the demo activation link on the pricing page.

WHAT WORKS NOW
- Public marketing homepage
- Registration and secure password hashing
- Login/logout
- Subscription gate
- Demo membership activation
- Profile-based region/cause grant matching
- Search and cause filters
- Deadline countdowns
- Document Vault uploads for PDF/DOC/DOCX
- Profile editing
- Responsive mobile and desktop layouts

PRODUCTION CONNECTIONS STILL REQUIRE YOUR ACCOUNTS
- Stripe Checkout product links and webhooks
- Airtable API/base credentials, if you want Airtable as the live database
- Make.com scenario and SendGrid/MailerLite credentials
- Final legal Privacy Policy and Terms

RECOMMENDED STRIPE WEBHOOK LOGIC
On checkout.session.completed or customer.subscription.updated, find the user by email and set subscription_status to Active.
On customer.subscription.deleted or payment failure, set subscription_status to Past Due.

SECURITY NOTE
This package is suitable as a working hosted MVP. For a larger public launch, move users and files to a managed database/private storage service, add email verification, password reset, rate limiting, and malware scanning for uploads.

GRANT CRAWLER INTEGRATION
-------------------------
The api/import-approved-grants.php endpoint receives approved grants from the separate GrantSpotter Crawler service.
Before use, open that file and replace IMPORT_SECRET with a long random secret. Use the identical value as WEBSITE_IMPORT_SECRET in the crawler environment.
