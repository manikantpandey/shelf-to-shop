# Design plan

Revision 2, Oct 27, 2026, written before the redesign code. Scope: the `web/` PWA (seller app and public shop
page). Tokens live in `web/src/styles/app.css`; if code and this document disagree, fix one of them in the same
change.

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

- **Display: Anek Devanagari** (Ek Type, OFL, self-hosted variable font with width 75–125 and weight 100–800).
  It covers Latin and Devanagari in one designed family, so English and Hindi signboards match. Signboard
  lettering: width 78, weight 750, tight leading. Screen titles: width 88, weight 650.
- **Text: Noto Sans + Noto Sans Devanagari** (unchanged) for body, inputs and **all prices**, with tabular
  lining figures (`font-variant-numeric: tabular-nums`), so price columns line up.
- Scale (px): 13 · 15 · 17 (body) · 20 · 24 · 30 · 40. Signboard 30 (phone) / 34 (desktop); tag price 20 on
  tiles, 40 in the item sheet. `:lang(hi)` text gets 1.06× size and 1.6 line height so matras never clip.
- No all-caps labels. Section headings are sentence case at 20/650 in Anek.

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
