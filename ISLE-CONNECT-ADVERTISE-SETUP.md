# Isle Connect: advertising and island launch (Saint Lucia, Barbados, Grenada)

## 1. Make your payment links (about 20 minutes, no code)
You need one link per package. **Stripe Payment Links** are the easiest:
1. Stripe Dashboard > Payment Links > Create. Add a product such as "Isle Connect: Boost 30 days" with a one-time price of US$40.
2. Add a custom text field called **"Your post's title or link"** so you know which post to boost. Stripe collects the buyer's email automatically.
3. Set the confirmation message to: "Thank you! We will boost your post (usually within one working day). Questions? Use Ask a question on Isle Connect."
4. Copy the link (it starts `https://buy.stripe.com/`). Repeat for each package: 7 days $15, 30 days $40, 90 days $90, Featured job $25, Event bundle $30, All-islands campaign $300.
(PayPal works too: create a PayPal payment link for each package, or use a PayPal.me link with the amount.)

## 2. Put the links on the site
Open `index.html` in a text editor, find `PAYMENT_LINKS` near the top of the script (just under the legal settings), and paste each link between the quote marks:
`const PAYMENT_LINKS = {boost7:"https://buy.stripe.com/...", boost30:"...", ...};`
A package with a link shows **Pay by card**. A package left as `""` shows only **Request this package**. Only https links are used. You can also change prices, wording and the `AD_TURNAROUND` promise ("usually within one working day") in `AD_PACKAGES` just below. Upload the file again.

## 3. When someone pays or sends a request
- **Requests** arrive in your admin **Questions** tab, tagged "Advertising", with the package, business, island and post title. Use **Reply by email**.
- **After payment is confirmed**, open **Review posts**, find their post, and use **Boost visibility**: 7, 30 or 90 days for the boosts, 30 days for a featured job, 14 days for an event bundle. For an all-islands campaign, use **Post to all** and choose a pin length.
- Ask the buyer to post for free first, so there is a post to boost.

## 4. Add the island guides
In the Supabase SQL Editor, run `isle_connect_island_guides.sql` (after `supabase_scraper.sql`). It is safe to run twice. It adds 19 posts: how to get a passport, driver's licence, birth certificate and government job in Saint Lucia; passport, driver's licence, certificates, hurricane shelters and police certificate in Barbados; passport, overseas documents and hurricane preparedness in Grenada; and a welcome post and a safety post for each island. Each links its official source. The how-to guides hide themselves on **31 October 2027** so old fees do not stay up.
I could not find official pages for a Grenada driver's licence or birth certificate, or a Saint Lucia emergency-management page, so those guides are not included. Do not add numbers or fees from memory.

## 5. A launch plan for three islands
- Every island page now has a **Share on WhatsApp** button. Send each island's link to friends, family and community groups with one useful guide, for example "How to apply for a Saint Lucia passport". People share practical posts far more than ads.
- Join Facebook and WhatsApp community groups for each island and post helpful links first, not advertisements, and follow each group's rules.
- Contact 40 to 50 local businesses per island by WhatsApp or Instagram. Offer a boost, show them their island page, and ask for a testimonial.
- Search engines cannot index single-page sites like Isle Connect, so do not wait for Google. Use messages, groups, radio and a QR code on flyers.

## 6. Check before you rely on it
- The refund rule on the Terms page (full refund if we decline or cannot run an ad; none once live) is a sensible default, not legal advice. Change it in the Terms text if you want something different.
- Fees and rules in the guides were read from official pages on 15 October 2026. They change: re-check each guide before its expiry date.
- Prices are my estimates. Raise them as your traffic reports justify.
