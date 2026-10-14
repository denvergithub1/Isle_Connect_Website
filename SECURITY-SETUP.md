# Isle Connect security setup

## What is protected, and how well
| Goal | What was built | Strength |
|---|---|---|
| Stop bulk copying of phone numbers and emails | Contact details are no longer in the public list. One is fetched per click, 40 per hour per visitor (`supabase_security_hardening.sql`) | **Strong** |
| Stop spam and flooding | Server-side limits per visitor: 5 posts, 5 sign-ups, 10 questions, 30 ratings per hour. Admin and your import script are never limited | **Strong** |
| Stop tracking via post media | Posts can only use photos/audio uploaded to your own Supabase storage (enforced in the database and the page) | **Strong** |
| Stop third parties profiling visitors | Strict Content-Security-Policy (no third-party scripts, fonts or trackers), no cookies, `no-referrer`, Google Fonts removed, Permissions-Policy blocks sensors/cameras/etc., Do Not Track and Global Privacy Control respected | **Strong** (flags: see below) |
| Stop framing / clickjacking | `frame-ancestors 'none'` header + a page-level guard | Strong with the headers file, basic without |
| Stop upload flooding | Photos 10 MB, audio 10 MB, video 25 MB max per file, only accepted file types, 15 uploads per hour per visitor where Supabase passes the visitor address (otherwise the limits below are your backstop), and every post stays hidden until you approve it. Rejecting or deleting a post also deletes its uploaded files | **Good**, not perfect |
| Block casual scrapers | Automation browsers (Selenium/Playwright) are not shown posts; robots.txt asks AI crawlers to stay out | **Weak**: only stops lazy tools |
| Stop determined scrapers copying public post text | Cannot be fully done for any public website. Use Cloudflare (below) to slow and challenge them | **Partial** |

## Do these in order
1. Run `supabase_security_hardening.sql` in the Supabase SQL Editor **and upload the new `index.html` at the same time**.
2. Upload `_headers` (Netlify / Cloudflare Pages) or `.htaccess` (Apache) next to `index.html`, and `robots.txt` to the site root.
   Other hosts (GitHub Pages, etc.) cannot set headers: put the site behind Cloudflare and add the same headers as a Transform Rule.
3. Supabase dashboard -> Project Settings -> API -> **Max rows**: set to 200 (the site never loads more than 300 per island).
4. Supabase -> Authentication -> turn OFF "Allow new users to sign up". Add two-step login to your admin account if your plan allows.
5. Put the site behind Cloudflare (free plan is enough): turn on **Bot Fight Mode**, add a **Rate limiting rule** (e.g. 100 requests per minute per visitor), and consider **Turnstile** if spam continues.

## Flags and privacy
Country flags are loaded from flagcdn.com, which can see a visitor's IP address. If you want zero third-party requests,
set `USE_FLAG_IMAGES = false` in `index.html` (flags become country-code badges) and remove `https://flagcdn.com` from the policy.

## If the site shows "demo data" after deploying
The page checks the Supabase library with an integrity hash. If you changed the library version or address, remove the
`integrity="..."` attribute from that `<script>` tag (or recompute the hash). Also check the browser console (F12) for blocked requests:
a custom Supabase domain must be added to `connect-src`, `img-src` and `media-src`.

## Videos: what to watch
- Videos are the heaviest thing visitors can upload. Supabase's free plan gives 1 GB of storage in total, so a few dozen 25 MB videos fill it. Check Dashboard > Storage after launch, and raise or lower the limit in `supabase_post_videos.sql` (26214400 = 25 MB).
- Uploaded files are public by their address as soon as they upload, even before you approve the post (the page only shows them once approved). Reject or delete anything harmful: that removes the files too.
- Only the file type declared by the browser is checked. Look at each video in the admin screen before approving it.

## Limits to know about
- Anything shown to the public can be copied by a person with a screenshot. These measures stop bulk and automated copying, not manual copying.
- Visitor limits use the address Supabase sees; people sharing one network (a school, an office) share a limit.
- The visitor rating uses a random id stored in the visitor's browser to stop repeat votes: it is only created if they rate a post.
