# Design plan

Revision 4, Oct 29, 2026 (revision 3 was Oct 28, revision 2 Oct 27). Scope: the `web/` PWA (front door, seller
app and public shop page). Tokens live in `web/src/styles/app.css`; if code and this document disagree, fix one of
them in the same change.

## Revision 4: a front door, and motion that answers a tap

The owner asked for the frontend to take ideas from six reference galleries. Until now a visitor to the site's
address landed on a sign-in form, which says nothing about what the product does; judges, and sellers who tap a
link someone shared, need that first. What each source gave us, and what we left out:

| Source | What it collects | Taken | Left out, and why |
|---|---|---|---|
| Landdding | Real landing pages | The product's own screen next to the headline; one idea per band; proof with real numbers | Logo walls and testimonials (we have neither); big-number cards with gradients (avoid list) |
| Modulify | Ready-made site sections | An order of sections: hero, what you get, proof, details, footer. No section was copied | The template look of identical cards |
| Motionin | Interactive hero and showcase sections | One product showcase that plays: the demo phone | Scroll-driven choreography, 3D and cursor effects: too heavy for a 2 GB phone, and motion must answer a tap or show the pipeline |
| 60fps | Animations from shipping apps | A tab mark that slides to the tapped tab; Add turning into a quantity stepper; a count that bumps; a stamp when a price is fixed; a progress bar that fills; a ring that empties as recording time runs out | Confetti, mascots, idle loops |
| Footer | Website footers, filterable by "Large type" and "Typographic" | A full-width large-type footer: the app's own signboard at street level | Marquees and animated footers |
| Recent | Design feed incl. OG images and a receipt component | A 1200×630 link preview from real product photos; the receipt slip for "what you get" | A launch video (follow-up) |

**The front door (`/`)**. Signed-in sellers go straight to Home; the installed app starts at `/home`.

```
FRONT DOOR (phone)               FRONT DOOR (laptop)
┌──────────────────────────┐     ┌───────────────────────────────────────────────┐
│[SHELF-TO-SHOP]     हिंदी │     │[SHELF-TO-SHOP]                         हिंदी │
│Your shop's catalog       │     │Your shop's catalog          ┌──────────┐      │
│from one video            │     │from one video               │demo phone│      │
│Walk past your shelf ...  │     │Walk past your shelf ...     │record,   │      │
│[ Try the sample shop   ] │     │[Try the sample shop][Start] │check,    │      │
│[ Start your own shop   ] │     │                             │share     │      │
│ ┌──────────┐             │     │                        (1)(2)(3)  ▶ caption   │
│ │demo phone│ (1)(2)(3) ▶ │     ├───────────────────────────────────────────────┤
│ └──────────┘             │     │What one video gives you       ┌~receipt~┐     │
├──────────────────────────┤     ├───────────────────────────────────────────────┤
│What one video gives you  │     │When it is not sure, it asks                   │
│ ┌~~~~ receipt ~~~~┐      │     │21 of 21 │ 0 │ 3 │ 26 min      (ruled ledger)  │
│ │Shop page ....  1│      │     ├───────────────────────────────────────────────┤
│ └~~~~~~~~~~~~~~~~~┘      │     │Made for the counter: three ruled rows         │
│When it is not sure, asks │     ├───────────────────────────────────────────────┤
│21 of 21 │ 0 │ 3 │ 26 min │     │board green: closing line, button, links       │
├──────────────────────────┤     │╔═════════════ SHELF-TO-SHOP ═════════════════╗│
│board green footer, links │     │╚═════════════════════════════════════════════╝│
│╔═ SHELF-TO-SHOP ═╗       │     └───────────────────────────────────────────────┘
└──────────────────────────┘
```

- **Demo phone**: a working miniature built from the real screens' tokens, not a screenshot. Record shows a camera
  view of hanging strips of packs, built only from the sample shop's cut-outs (no hand, no shop interior, at the
  owner's request), with the seller's Hinglish words appearing as they are spoken; then the focus brackets lock
  on the pack and "₹4 heard at 0:19" stamps in. Check shows the three items found, with the
  evidence line ("you said 'same pricing': ₹4; the pack says ₹5, so it shows as MRP"). Share shows the shop page,
  two items in the basket and the order message. It plays once when it comes on screen and stops on the shop;
  the three numbered steps (a true sequence) jump to a step; a button pauses or plays again (WCAG 2.2.2). Under
  reduced motion it never plays by itself and every element is shown in its final place.
- **Receipt**: what one video gives, printed like a billing-machine slip: torn edges, dotted leaders, a ruled
  total ("Typing: none"). Structure from the receipt, no fake shop details.
- **Proof**: the eval figures from `evals/report.md` in one ruled ledger row, with the honest wording ("3 of the
  videos are from a real kirana shop") and a link to the full table.
- **Footer**: board green, the closing line and the one button, the links, then the signboard as wide as the
  screen. It is the only large type on the page.
- **Link preview** (`/og.png`, 1200×630): the signboard, the headline and the three tagged products on board
  green. `index.html` points to it with an absolute address (`VITE_SITE_URL`). Shop pages share this preview
  for now; a per-shop preview needs a page rendered on the server (open question 5 in the plan).
- Fixed on the way: the browser theme colour, the manifest colours and the app icon were still revision 1 blue.
  They are now board green with the marigold tag.

**Motion rules, revision 4**. Still only in answer to a touch or to show the pipeline, all off under
`prefers-reduced-motion`:

- Buttons, chips and tiles press in slightly (scale 0.97, 120 ms).
- Tab bar: the mark under the current tab slides to the tapped tab (a view transition on tab taps only; the
  page itself does not fade).
- Shop page: Add turns into the quantity stepper; the basket bar rises when the first item goes in; its count
  bumps on each change. A basket restored on reload does not animate.
- Review: when a question is answered, the item's new price tag lands with a stamp.
- Processing: a bar fills as steps finish ("3 of 8 steps done"); a finished step's number becomes a drawn tick.
- Recorder: a marigold ring around the record button empties as the 60 seconds run out.
- The landing demo is the one thing that moves without a tap. It shows the pipeline, runs once, and can be paused.

Checked against the avoid list: no gradient washes, glass or neon; no eyebrow labels or "→" buttons; the only
numbered markers are the demo's three steps and the pipeline (true sequences); no fade-and-slide on scroll (the
bands below the hero do not move at all); no sparkle icons or "AI magic" copy ("When it is not sure, it asks");
no emoji. The phone mock and the bubble have the only new shadows, because they stand for objects.

## Revision 3: running the shop, not just making the catalog

Trying revision 2 as a shopkeeper, the owner asked for "management options" and a better font. Looked at from the
counter, three gaps stood out: prices and stock change every week but could only be edited one item at a time;
customers could only order one item per message, while a kirana order is a list; and nothing told the customer
when the shop is open, whether it delivers, or how to pay. Chosen with the owner (all options taken):

- **Stock and prices**: a sold-out switch on every item tile, select many items to mark sold out, hide, move or
  change the price by rupees or percent; add an item by hand (name, price, MRP, section, then a photo).
- **Sections**: items grouped by category into sections (Snacks, Cold drinks, ...) that the seller renames in
  English and Hindi, reorders and adds to; "show at the top" pins an item; "hide from shop" keeps it off the page.
- **Offers and MRP**: MRP shown struck through next to the shop's price (and sent to Meta as `sale_price`); an
  offer strip across the top of the shop page.
- **Shop profile**: hours, address, pickup or delivery, delivery note, minimum order, UPI ID, shop photo, about.
- **Basket orders**: customers add items with quantities and send one numbered WhatsApp message with the total;
  the server prices the basket from the published shop. Every order also lands in an **order book** (new, packed,
  delivered, paid) with today's sales.
- **Share kit**: QR code, a printable counter poster, and a WhatsApp Status picture of any item.
- **Navigation**: phones get Home, Items, Record, Orders and More (Videos, Shop profile, Sections, Share kit,
  Settings); laptops list everything in the sidebar, with a count of new orders.
- **Font: Poppins** (chosen with options over Mukta, Baloo 2 and keeping Anek + Noto): friendly geometric letters
  from an Indian foundry, one family for English and Hindi, familiar from Indian apps. It replaces both Anek
  (signboard, headings) and Noto (text); the signboard keeps its board, border and capitals, now in Poppins 700.
- Home now puts what needs the shopkeeper first (new orders, then questions), then "Your shop" (link, share,
  downloads), then the week's numbers.

Checked against the avoid list again: the order book uses ruled lines and a dashed total rule from a receipt,
not cards with shadows; numbered markers still appear only for the pipeline steps; no new colours were added
(the offer strip is marigold, which already means "price and offer").

## 0. Why revision 2

The first build followed revision 1 (white sheets on a cool grey "ledger", one blue, ruled rows). Seen as a whole
at 360×800 and on a laptop it read as an unstyled form. The seller-owner of the project rejected it for the
hackathon demo, for four reasons we agree with:

1. **No home and no history.** After publishing there was nowhere to see past videos, all items, or whether
   anyone visited the shop.
2. **No identity.** Grey, white and one blue; nothing says "shop".
3. **No laptop layout.** A 560 px phone column floating in grey; judges watch on a projector.
4. **Ugly demo data.** Synthetic colour-bar test images on every screen. (Fixed outside the UI: the sample shop
   is built from real kirana videos with the real models.)

Chosen direction (asked with options): **Bazaar bright**, a home screen with shop numbers, video history, all
items and per-video run details, a full desktop layout, and real clips as demo data. Also asked: weak photos can
be replaced by the seller's own photo, a better moment from the same video, or an Open Food Facts pack photo.

## 1. Subject and audience (unchanged)

**Subject**: a small Indian shop's stock, turned from one walk-past video into a catalog customers order from on
WhatsApp. **Seller**: owner of a kirana, saree, footwear or handicraft shop; budget Android phone, bright light,
often one-handed, often Hindi-first; checks the app between customers. **Buyer**: taps the shop link in a
WhatsApp chat, wants photo, price and one tap to order. **Judges** (new): see it on a laptop or projector for
three minutes and need to understand what happened to the video.

## 2. The idea: the shop's signboard

Every Indian shop has a painted name board: deep green or red, big condensed letters in yellow or white, a thin
painted border, the name and nothing else. That board is the app's one bold element. It carries the shop's name:

- on the seller's Home (phone: top of the screen; laptop: top of the sidebar),
- on the public shop page header, so the buyer sees the shop's own board,
- on sign in, carrying the product name.

The second strong element is the **price tag**: marigold fill, ink figures, a notched left edge like a hang tag,
used wherever a price is shown on a product photo. Everything else is quiet: white surfaces on a pale green-grey
ground, ink text, hairline rules.

Sources used for structure, not decoration: painted signboards (board, border, condensed letters), hang tags
(notch, big figures), the bahi-khata (ruled rows of figures for numbers and run details). Not used: marigold
garlands, rangoli, paisley, textures, handwriting fonts, illustrations of shops.

## 3. Colour

Six named tokens and three derived ones. Ratios use the WCAG 2.x formula and were computed, not estimated.

| Token | Hex | Role |
|---|---|---|
| `board` | #0F4C3A | Signboards, sidebar, primary buttons, links, focus ring, selected state |
| `marigold` | #F6B526 | Price tags, signboard lettering and border, the Record button, active nav mark |
| `paper` | #FFFFFF | Surfaces: tiles, panels, sheets, inputs, top and bottom bars |
| `ground` | #EEF1EC | App background (pale green-grey; not cream) |
| `ink` | #17201C | Text, prices, icons |
| `sindoor` | #B42318 | Errors, "needs a check", destructive actions (never decoration) |
| `ink-2` (derived) | #4B5751 | Secondary text |
| `line` (derived) | #D5DBD5 | Hairline rules and input borders (non-text) |
| `tint` (derived) | #E2EEE7 | Selected rows, chip fills, the chart's grid |

| Pair | Ratio | Use |
|---|---|---|
| ink on paper / ground / tint | 16.7 / 14.6 / 14.0 | body text |
| ink on marigold | **9.2 (AAA)** | prices on tags, Record button label |
| paper on board | 9.9 | button labels, sidebar text |
| marigold on board | 5.5 | signboard lettering (large, bold) |
| board on paper / ground | 9.9 / 8.7 | links, outline buttons |
| ink-2 on paper / ground | 7.6 / 6.6 | secondary text |
| sindoor on paper / ground | 6.6 / 5.8 | errors, check marks |
| marigold on paper | 1.8 | **never as text**; fill only |

Status never relies on colour alone: every state has a word ("On shop", "Sold out", "2 questions").

## 4. Type

- **Poppins** (Indian Type Foundry, OFL, self-hosted at 400, 500, 600 and 700; Latin and Devanagari) for
  everything since revision 3. Signboard: 700, capitals, slight tracking. Headings: 600. Body: 400 at 16 px.
  Labels and buttons: 600 to 700. Prices: 700 on the marigold tag.
- Scale (px): 13 · 15 · 16 (body) · 17 · 20 · 24 · 30 · 40. Signboard 24 (phone) / 30 (shop page on laptops);
  tag price 20 on tiles, 40 in the item sheet. `:lang(hi)` text gets 1.65 line height so matras never clip.
- No all-caps labels (the signboard's capitals are the shop's name, as painted).
- Revision 2 used Anek Devanagari (display) with Noto Sans (text); replaced at the owner's request.

## 5. Space, radius, depth

Spacing 4 · 8 · 12 · 16 · 24 · 32 · 48. Tap targets ≥ 48 px. Radius by hierarchy: tags 0 with a notch · tiles 6
· inputs 8 · buttons 10 · panels 12 · sheets 16 (top corners on phone) · pills and the Record button fully round.
Depth: panels and tiles are separated by `line` hairlines, not shadows. Only the bottom sheet / side panel and the
raised Record button have a shadow.

## 6. Layout

Phone (< 900 px): a top bar (Home shows the signboard instead), content, and a bottom bar with five places:
Home, Items, **Record** (raised marigold circle in the middle), Videos, Settings. One primary action per screen,
pinned above the bottom bar where it exists. Desktop (≥ 900 px): a 248 px `board` sidebar with the signboard,
the Record button and the four places; content on `ground`, max 1120 px, page title with the primary action on
its right; grids widen to 3–5 columns; the item editor becomes a right-hand panel instead of a bottom sheet.
Text is left-aligned everywhere; only the signboard is centred.

```
HOME (phone)                         HOME (desktop)
┌───────────────────────────┐        ┌──────────┬──────────────────────────────────────────┐
│╔═════════════════════════╗│        │╔════════╗│ Home                      [Share on WA] │
│║  SHARMA GENERAL STORE   ║│ board  │║ SHARMA ║│ ┌ needs you ────────────────────────┐   │
│╚═════════════════════════╝│        │║GENERAL ║│ │ 1 video has 2 questions  [Check]  │   │
│ 8 items on your shop      │        │╚════════╝│ └───────────────────────────────────┘   │
│ [Share on WhatsApp] [Copy]│        │ (● Record)│ This week  Visits 24 │ Orders 6 │ Items 8│
├───────────────────────────┤        │ Home     │ ▁▃▂▅▇▃▆  visits by day, orders marked   │
│ 1 video has 2 questions › │ sindoor│ Items    │ Most ordered        Recent videos       │
├───────────────────────────┤        │ Videos   │ 1 Pepsi  3          [thumb] Today 3 items│
│ This week                 │        │ Settings │ 2 Slice  2          [thumb] Today 5 items│
│ Visits 24 │Orders 6│Items 8│ ledger │          │                                          │
│ ▁▃▂▅▇▃▆                   │        │          │                                          │
│ Recent videos       All › │        └──────────┴──────────────────────────────────────────┘
│ [thumb] Today, 0:24 3 items│
├───────────────────────────┤
│ Home Items (●) Videos More│
└───────────────────────────┘

ITEMS                               ITEM SHEET (phone) / PANEL (desktop)
┌───────────────────────────┐       ┌───────────────────────────┐
│ Items            [search] │       │ [   photo   ]  ◤₹40       │
│ (All 13)(On shop)(Sold out)│      │ Change photo:             │
│ ┌─────┐┌─────┐            │       │ [Take or upload photo]    │
│ │photo││photo│            │       │ [Pick a moment in video]  │
│ │◤₹40 ││◤₹20 │ tags       │       │ [Find pack photo]         │
│ │Pepsi││Slice│            │       │ Price ₹ [ 40 ]            │
│ └─────┘└─────┘            │       │ Name    [ Pepsi 750 ml ]  │
│ Sold out shows a band     │       │ [x] Sold out              │
└───────────────────────────┘       │ [Save]       Remove item  │
                                    └───────────────────────────┘
VIDEO DETAIL (judges' screen)        PUBLIC SHOP
┌───────────────────────────┐       ┌───────────────────────────┐
│ Video, today 7:31 pm      │       │╔═════════════════════════╗│
│ 0:24 long, 3 items, 52 s, │       │║  SHARMA GENERAL STORE   ║│
│ cost $0.09                │       │╚═════════════════════════╝│
│ What we heard             │       │ Order on WhatsApp. Prices │
│ 0:01 "ye nut cracker ..." │       │ ┌─────┐┌─────┐            │
│ Steps (true sequence)     │       │ │photo││photo│            │
│ 1 Checking video  2 s     │       │ │◤₹40 ││◤₹20 │            │
│ 2 Finding items  31 s Spark│      │ │Pepsi││Slice│            │
│ ...                       │       │ │[Order on WhatsApp]      │
│ Items and evidence        │       │ └─────┘└─────┘            │
│ [frame] ₹4 heard at 0:08  │       └───────────────────────────┘
│  "chaar rupaye mein"      │
└───────────────────────────┘
```

Record, Processing and Review keep their jobs from revision 1 and take the new tokens: the recorder stays a dark
full-screen camera with the marigold shutter; Processing shows the eight pipeline steps as a numbered list (a true
sequence) with the running step marked; Review keeps the yellow tag grid and the question list.

## 7. Review against the "avoid" list, and what changed

1. **Stats as big-number cards with gradients** (the default dashboard look) → replaced by one ruled "ledger
   strip" of three figures in tabular numbers and a plain 7-day bar chart with orders marked on it. No cards,
   no gradients.
2. **Identical rounded cards with one soft shadow** → radius varies by hierarchy (section 5); tiles and panels sit
   on hairlines; shadows only on the sheet and the Record button.
3. **Cream + serif + terracotta / dark + neon** → white and pale green-grey with a deep green board; marigold only
   as fill. Checked: not cream (#EEF1EC is green-grey), no serif.
4. **Numbered markers** → only the pipeline steps on Processing and Video detail (a real sequence).
5. **Eyebrow labels, "A · B · C" meta strings, "→" on buttons** → none. Meta text is written as a sentence
   ("0:24 long, 3 items, 52 seconds").
6. **Sparkles, "AI magic" copy** → the assistant is described by what it did ("Heard ₹4 at 0:08"); photos with
   generated backgrounds say "AI background"; pack photos say "Photo: Open Food Facts".
7. **Fade-and-slide-up on every section** → no entrance animation. Motion: the running pipeline step, the sheet
   opening, the Record button's pulse while recording; all off under `prefers-reduced-motion`.
8. A first sketch put the signboard on every screen; cut to Home, the sidebar, sign in and the public shop, so it
   stays special.

## 8. Copy

Plain shop words, sentence case, active verbs, the same name for the same action everywhere: Record, Use this
video, Fix prices, Publish, Share on WhatsApp, Order on WhatsApp, Change photo, Sold out, Remove item. Errors say
what happened and what to do. Hindi strings are written, not machine-literal, and every key exists in both files
(a test checks).

## 9. Quality floor

Responsive from 320 px; visible focus ring (2 px `board` + 2 px offset, `marigold` on the sidebar); labels for
screen readers on icon buttons; works on a 2 GB phone (no chart library: bars are plain elements; fonts are
subset by unicode range). Screenshots of every screen at 360×800 and 1440×900 are taken and critiqued before the
work is called done (`docs/screenshots/`).
