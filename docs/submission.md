# Hackathon submission text

Meta Global AI Developer Hackathon, Startup track. Copy the parts the form asks for.

**Project name:** Shelf-to-Shop

**Tagline (short):** One shelf video in, a WhatsApp shop out.

**Links**
- Live demo: https://shop.shankhyaai.com ("Try the sample shop" opens a private copy)
- Source (Apache-2.0): https://github.com/manikantpandey/shelf-to-shop
- Demo video: (add the link)

## The problem

Small Indian shops (kirana stores, sarees, footwear, handicrafts) already sell through WhatsApp and
Instagram, but almost none has a catalog. Entering every product with a name, price and photo, one by one,
on a budget phone, between customers, is the step that never gets done. So customers ask "price kya hai?"
in chat, item by item, and the shop cannot use Instagram product tags or the WhatsApp catalog at all.

## What it does

The shopkeeper walks past the shelf for under a minute with the phone camera on, saying prices out loud
in Hindi, English or both ("ye neela wala 1200, cotton wala 850"). Shelf-to-Shop turns that one video into:

- **A shop page** customers open from a link or QR code: sections, search, MRP and offers, pickup or
  delivery. Customers fill a basket and send one numbered order on WhatsApp, with the total.
- **An order book**: new, packed, delivered, paid, with today's sales.
- **A Meta catalog feed** that Commerce Manager refreshes every hour, for Instagram product tags and the
  WhatsApp catalog.
- **Clean product photos**: each item cut out on a fresh background, with the product's own pixels kept
  exactly and the AI-made background labelled.
- **Offers**: a Diwali or weekend sale in one screen; prices drop on the shop page and come back on the
  end date, and a ready message goes to customers through the shopkeeper's own WhatsApp.

Before anything goes live the shopkeeper checks it. Where the system is unsure (a price said above the
printed one, two items that look alike, a weak photo) it asks a short question instead of guessing.
Every screen works in Hindi and English.

## How it uses Meta's models

| Step | Model |
|---|---|
| Find each item, read price tags, pair each spoken price with the item on screen (video and audio together) | Muse Spark 1.3 |
| Cut out each item from the box Muse Spark found | SAM 3.1 |
| Hear the prices with timing, Hindi with English code-switching | Muse Voice Transcribe 1.0 |
| Titles, category, colour, material and descriptions in English and Hindi | Muse Spark 1.3 (text) |
| A clean backdrop; the original product pixels are composited on top | Muse Image 1.0 |

Prices are decided by our own matcher, which weighs the spoken price, Muse Spark's pairing and the printed
tag, and keeps the evidence (the words heard and the moment in the video) for every price.

## Results

On four labelled shelf videos (three from a real kirana shop, one with deliberate traps): **21 of 21 items
found**, 17 of 20 prices right, the other 3 turned into questions, and **0 wrong prices published without
asking the shopkeeper**; all 5 seeded traps caught. Reading 138 seconds of video cost $0.45 in model calls
(about $0.10 per 30-second video) and saves an estimated 26 minutes of typing. The eval set is small and
the matcher was tuned on it, so these numbers are a sanity check, not a benchmark.

## How it is built

FastAPI and SQLAlchemy (Postgres) with a database-backed job queue and an engine whose pipeline stages are
cached and resumable; a React PWA with an in-browser recorder and resumable uploads; Docker Compose on one
AWS server with automatic HTTPS. Security and privacy were built in, not added: per-shop data isolation
with tests, strict content security policy, spend caps per job, per shop and per day, model inputs treated
as data never instructions, consent before recording, raw videos deleted after 7 days, and one-click export
and delete (India's DPDP Act). Images with AI backgrounds carry IPTC metadata and a visible label.

## Challenges

- Muse Image has no mask input, and an edit test changed 43% of the product's pixels, so we generate only
  the backdrop and composite the real product on top; a test checks the pixels are byte-identical.
- Voice Transcribe gives turn-level timing only, so we split the audio on pauses and parse Hindi numbers
  ("ek hazaar do sau", "saadhe aath sau") ourselves.
- Packs printed "₹5" that the shop sells at ₹4 made every item look like a conflict until the matcher
  learned to read a lower spoken price as a discount off the MRP.

## What's next

Email sign-in (the demo uses a sample-shop sign-in), instant catalog updates through Meta's API, a
per-shop link preview, more labelled videos from more kinds of shops, and the SocialPulse integration
(designed in docs/integration/phoenix.md) so an assistant can run the same engine as a tool, with the
shopkeeper still approving every publish.

**Built during the hackathon (Oct 27 to Nov 4, 2026).** Every line of the repository was written during the
event.
