# Design plan

Status: approved direction, written before any UI code (Oct 27, 2026). Scope: the `web/` PWA (seller app and
public shop page). The tokens below become `web/src/styles/tokens.css`; if code and this document disagree, fix
one of them in the same change.

## 1. Subject and audience

**Subject**: stock-taking for a small shop. One slow walk past the shelves, prices said aloud, becomes a catalog
people can order from.

**Seller (primary user)**: owner of a small Indian shop (sarees, footwear, kirana, handicrafts) who already sells
through Instagram and WhatsApp. Budget Android phone (2–3 GB RAM, 720p screen, Chrome), often in bright sunlight
or under shop tube lights, often one-handed while the other hand moves stock. Often reads Hindi more comfortably
than English. Uses WhatsApp every day and does not want to learn a new tool.

**Buyer (secondary user)**: a customer who taps the shop link in a WhatsApp chat or an Instagram bio or story,
lands on the public shop page in an in-app browser on a slow network, and wants to see photo and price and order
in one tap. Never signs in.

What follows: white surfaces and near-black text, never colour alone; one primary action at the bottom; every
string in `src/i18n/{en,hi}.json` with Devanagari balanced to Latin; a small bundle and almost no motion; prices
as the hero data, because the seller checks them and the buyer decides on them.

**Sources of ideas**, used for structure and not as decoration: the bahi-khata ledger (red vertical margin rule,
ruled rows, columns of figures), shelf-edge price labels and hang tags (tag shape, notched corner, big figures),
receipt slips (plain lines of text). Not used: paper textures, stitched borders, rangoli, shop illustrations,
handwriting fonts.

## 2. One job per screen

| Screen | Route | Its one job | Primary action (pinned bottom) |
|---|---|---|---|
| Sign in | `/signin` | Get a one-time code by email and enter it | Send code, then Sign in |
| Consent | `/consent/account`, `/consent/recording` | Understand what is kept, why and for how long, and agree; recording consent warns against filming customers | I agree |
| Record | `/record` | Capture one walkthrough video of 60 s or less | Record / Stop; in preview: Use this video |
| Processing | `/jobs/:id` | Show where the job is and what happens next | None while running; Try again on failure; Review items when done |
| Review | `/jobs/:id/review` | Get every price right before publishing. **The one bold screen** | Fix 3 prices; Publish when nothing is open |
| Product edit sheet | sheet over Review | Correct one item's price and details from the evidence | Save |
| Catalog | `/catalog` | Share the published catalog; get the feed file and photos | Share on WhatsApp |
| Public shop | `/s/:slug` | Let a buyer order one item on WhatsApp | Order on WhatsApp, per row; nothing pinned |
| Settings | `/settings` | Keep shop details and the seller's data under their control | Save |
| Run log (secondary) | `/jobs/:id/log` | Show what each step did, its time and cost | None |

## 3. Colour

Six named tokens plus two derived ones. Ratios are measured with a short script using the WCAG 2.x relative
luminance formula (sRGB channel `c/12.92` if `c <= 0.04045`, else `((c+0.055)/1.055)^2.4`;
`L = 0.2126R + 0.7152G + 0.0722B`; ratio `(L1+0.05)/(L2+0.05)`). Re-run it whenever a hex changes.

| Token | Hex | Role | vs `sheet` | vs `ledger` |
|---|---|---|---|---|
| `sheet` | #FFFFFF | Surfaces: tiles, rows, sheets, inputs, footer bar | — | 1.14 |
| `ledger` | #EDF0F2 | App background behind surfaces (cool grey, not cream) | 1.14 | — |
| `ink` | #14181D | Text, prices, icons | 17.82 | 15.57 |
| `pen` | #1C3FAA | Primary button fill, links, outline buttons, focus ring | 8.97 | 7.84 |
| `tag` | #FFD338 | Price-tag fill, Review grid only | 1.44 | 1.25 |
| `rule` | #B3261E | Ledger margin rule, errors, "needs a check" outline, destructive actions | 6.54 | 5.71 |
| `ink-2` (derived) | #46505C | Secondary text, 1 px rules, input borders | 8.20 | 7.16 |
| `ok` (derived) | #1B6E3A | "Published" and "Saved" status text, always with a check icon | 6.29 | 5.50 |

Required pairs. AA 4.5:1 for body text; 3:1 for large text, component boundaries and focus rings; AAA 7:1 for
prices.

| Foreground on background | Ratio | Needed | Where | Result |
|---|---|---|---|---|
| `ink` on `sheet` | 17.82 | 7 (prices) | Body text; prices on the public page and edit sheet | Pass AAA |
| `ink` on `ledger` | 15.57 | 4.5 | Headings on the app background | Pass AAA |
| `ink` on `tag` | 12.42 | 7 (prices) | Price on a Review tag | Pass AAA |
| `ink-2` on `sheet` | 8.20 | 4.5 / 3 | Secondary text; input borders and rules | Pass AAA |
| `ink-2` on `ledger` | 7.16 | 4.5 | Secondary text on the app background | Pass AAA |
| white on `pen` (= `pen` on `sheet`) | 8.97 | 4.5 / 3 | Primary button label; links, outline buttons, focus ring | Pass AAA |
| `pen` on `ledger` | 7.84 | 4.5 / 3 | Links and focus ring on the app background | Pass AAA |
| `pen` on `tag` | 6.25 | 3 | Focus ring where it meets a tag | Pass |
| `rule` on `sheet` (= white on `rule`) | 6.54 | 4.5 | Error text, "needs a check" outline; label on the final delete button | Pass AA |
| `rule` on `ledger` | 5.71 | 4.5 | Error text on the app background | Pass AA |
| `ok` on `sheet` (= white on `ok`) | 6.29 | 4.5 | "Published 27 Oct, 4:20 pm"; white on `ok` reserved for a status chip | Pass AA |
| white on `ink` | 17.82 | 4.5 | Record screen labels on ink panels | Pass AAA |
| `pen` on `ink` | 1.99 | 3 | Focus ring on the record screen | **Fail**: white ring there (17.82) |
| `rule` on `ink` | 2.73 | 3 | Red record disc on the ink panel | **Fail**: disc sits inside a white ring, which is the boundary |

No core hex had to change: every text pair passes AA and both price pairs pass AAA. `ok` (#1B6E3A) is newly
chosen. The two failing pairs are solved by layout, not by changing colours.

Usage rules:
- One filled `pen` button per screen. Secondary actions are outline (`pen` text, 2 px `pen` border) or text links.
- `tag` yellow appears only on Review price tags: not on the public page, not for highlights or warnings.
- `rule` red means "look here" (errors, "needs a check", destructive actions); its one structural use is the
  public page margin rule. `ok` green always comes with a check icon and words.
- No alpha-blended text, gradients or tints; the only translucent fill is the 50% `ink` scrim behind the sheet.
- Light theme only in v1. The record screen is the one dark surface (solid `ink` panels; controls never sit on the
  video). Under `forced-colors: active` tag states stay readable because they carry an icon and words.

## 4. Type

**Families**: Noto Sans (Latin and ₹) and Noto Sans Devanagari, self-hosted variable woff2 via
`@fontsource-variable` (CSP keeps `font-src 'self'`). Subsets `latin`, `latin-ext` (₹ is U+20B9) and `devanagari`
only; `unicode-range` loads Devanagari only when it renders. `font-display: swap`; fallback `system-ui,
sans-serif`. Sizes in `rem` from a 16 px root, so the phone's text-size setting scales everything.

| Role | Used for | Latin px / weight / line height | Devanagari (`:lang(hi)`) px / line height |
|---|---|---|---|
| small | Labels, "AI background", evidence lines, times | 14 / 400 / 20 | 15 / 24 |
| body | Paragraphs, inputs, list text | 17 / 400 / 24 | 18 / 29 |
| strong | Buttons, row titles, product titles on tiles | 17 / 600 / 24 | 18 / 29 |
| title | Edit sheet title, section headings in Settings | 20 / 600 / 26 | 21 / 32 |
| heading | Screen headings ("Your catalog"), shop name | 24 / 700 / 30 | 26 / 38 |
| price | Prices on the public page and in the edit sheet field | 29 / 700 / 36, tabular | digits stay Latin: 29 / 36 |
| display | Record countdown, item count on Review | 35 / 700 / 40, tabular | 37 / 54 |
| price hero | Price on a Review tag | 40 / 700 / 44, tabular | digits stay Latin: 40 / 44 |

**Balancing the scripts**: at equal px Devanagari looks smaller and its matras clip at Latin line heights, so
under `:lang(hi)` every step is 6–8% larger (whole px) and line height goes from 1.4 to 1.6 for text (1.25 to
1.45 for headings); weights stay the same. Hindi runs longer, so no label relies on a fixed width.

**Prices and figures**: `font-variant-numeric: tabular-nums lining-nums` on prices, countdown, counts and
percentages. Prices use Latin digits with Indian grouping in both languages (the parser accepts Devanagari digits
as input), never wrap and are never truncated. On a narrow tag the price hero steps down by length: up to 6
characters (₹1,200) at 40, 7 (₹12,000) at 35, 8+ (₹1,20,000) at 29; thresholds confirmed at 320 px.

**INR format**: money is stored as integer paise. Whole rupees show no paise; anything else shows two digits.

```ts
const whole = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
const paise = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", minimumFractionDigits: 2 });
export const formatINR = (p: number) => (p % 100 === 0 ? whole : paise).format(p / 100);
```

Verified on Node 22: 85000 → `₹850`, 120000 → `₹1,200`, 1200000 → `₹12,000`, 12000000 → `₹1,20,000`,
119950 → `₹1,199.50`, in both UI languages. (The feed CSV's `1200.00 INR` comes from the engine.) Dates use
`Intl.DateTimeFormat` in the UI language.

## 5. Space, touch and shape

**Spacing scale** (px): 4 · 8 · 12 · 16 · 24 · 32 · 48 as `--space-1` to `--space-7`. Page gutter 16 (12 below
360 px). Tile padding 8; label to field 4; between form groups 24; between page sections 32. **Tap targets**:
48 × 48 px minimum, 8 px apart; full-width primary buttons 56 px tall; record button 72 px; rows at least 56 px.

**Thumb zone**: exactly one primary action per screen, a full-width filled `pen` button in a footer bar pinned to
the bottom (`sheet`, 1 px `ink-2` top rule, `env(safe-area-inset-bottom)` padding), optionally with one outline
secondary beside it (Retake + Use this video). Destructive actions reach the footer only in their confirmation
sheet; nothing used often sits at the top. Exception: the public shop repeats its one action per row.

**Radius by hierarchy** (structure gets none; larger, more temporary containers get more):

| Element | Radius |
|---|---|
| Page, ledger rows, Review grid tiles, photos, small labels | 0 |
| Inputs, selects, checkboxes | 4 |
| Buttons (filled and outline), segmented language switch | 8 |
| Bottom sheet | 16 on the top two corners only |
| Price tag | None: a 12 px 45° clipped notch on the top-left corner |
| Record button | Circle (camera convention; the only round control) |

**Elevation**: only the bottom sheet has a shadow (`0 -4px 16px rgb(20 24 29 / 0.25)`, over a flat 50% `ink`
scrim). Everything else is flat, split by 1 px `ink-2` rules (dark on purpose, 8.20:1, so they survive sunlight).

**Focus ring**: `:focus-visible { outline: 2px solid var(--pen); outline-offset: 2px; }` on light surfaces (8.97 /
7.84 / 6.25 on `sheet` / `ledger` / `tag`); `var(--sheet)` on the record screen's `ink` panels (17.82; `pen` there
is 1.99). Never removed. `clip-path` hides outlines, so a price tag's ring goes on its tile button.

## 6. Price tag component (Review grid only)

**Anatomy**: the tile is one `<button>` (`sheet`, radius 0): 1:1 photo, tag, title (strong, 2 lines max) and an
optional small caption. The tag spans the tile minus 8 px insets, is at least 56 px tall, and is cut with
`clip-path: polygon(12px 0, 100% 0, 100% 100%, 0 100%, 0 12px)`. Price `ink` 40/700 tabular, 16 px left padding
to clear the notch, stepping down as in section 4. Grid: 2 columns (3 from 600 px), 1 px `ink-2` rules, no gaps,
no shadows, in video order so the seller sees the shelf as they filmed it.

| State | Fill | Edge | Icon | Visible text | Accessible name (tile) |
|---|---|---|---|---|---|
| Confirmed | `tag` yellow | None | None | `₹1,200` | "Blue silk saree. Price ₹1,200." |
| Needs a check: missing price | `sheet` white | 2 px `rule` outline following the notch | "!" in a circle, `rule` | "Add price" (20/600 `ink`) | "Cotton print saree. Price missing. Needs a check." |
| Needs a check: conflict | `sheet` white | 2 px `rule` outline | "!" in a circle | `₹1,200 or ₹1,000?` (24/700 tabular, two lines; tag grows) | "Red bandhani saree. Heard ₹1,200, tag shows ₹1,000. Needs a check." |
| AI-edited background (any price state) | unchanged | unchanged | None | Caption under the title: "AI background" / "AI बैकग्राउंड" (small, `ink-2`) | adds "Background is AI-edited." |

"Needs a check" reads without colour: the filled tag becomes a blank white one with an icon and words, so a
greyscale screenshot still shows which tiles need work. The outline is two stacked clipped layers (outer `rule`,
inner `sheet` inset 2 px), since borders do not follow `clip-path`. Non-price flags use the same "!" + words on
the caption line ("Same as Blue silk saree?", "Check photo"), never on the tag.

## 7. Layout sketches (360 px wide)

`[ ]` filled or outline button, `[/ ]` yellow notched tag, `{/ }` blank "needs a check" tag, `┃` red margin rule.

```text
RECORD (recording)                    PREVIEW
┌──────────────────────────────────┐  ┌──────────────────────────────────┐
│ 0:42 left           ● Recording  │  │ Check your video          0:52   │
├──────────────────────────────────┤  ├──────────────────────────────────┤
│                                  │  │                                  │
│                                  │  │                                  │
│           live camera            │  │          video preview           │
│        (rear, up to 720p)        │  │          (tap to play)           │
│                                  │  │                                  │
│                                  │  │                                  │
│ ┌────────────────┐               │  │ Play it once. Can you hear       │
│ │ Move slowly    │               │  │ each price clearly?              │
│ │ Say each price │               │  │                                  │
│ └────────────────┘               │  │                                  │
├──────────────────────────────────┤  │                                  │
│ Mic ▮▮▮▮▯▯  Good                 │  │                                  │
│                                  │  │                                  │
│ [Torch]       (( ● ))            │  │                                  │
│                Stop              │  │                                  │
│                                  │  ├──────────────────────────────────┤
│       Upload from gallery        │  │ [ Retake ]  [ Use this video  ]  │
└──────────────────────────────────┘  └──────────────────────────────────┘
```

- Record: solid `ink` panels above and below the feed; countdown 35/700 tabular, white, hard stop at 60 s (idle:
  "Up to 60 seconds", button "Record"). Mic meter: six segments plus a word ("Good", "Speak louder" after 2 s of
  quiet, "Too loud"). Torch: 48 px toggle, shown only if the track supports `torch`. Record button: white ring
  around a `rule` red disc (square while recording). "Upload from gallery" opens `<input type="file" accept="video/*">`.
- Preview plays the IndexedDB copy. "Retake" is outline; "Use this video" is filled and starts the upload.

```text
PROCESSING                            REVIEW (the bold screen)
┌──────────────────────────────────┐  ┌──────────────────────────────────┐
│ Making your catalog              │  │ Found 12 items                   │
│ 52 s video, started 4:10 pm      │  │ 3 prices need a check.           │
├──────────────────────────────────┤  ├────────────────┬─────────────────┤
│ 1  Checking video        ✓ Done  │  │                │                 │
│ 2  Finding items         ✓ Done  │  │     photo      │     photo       │
│ 3  Hearing prices        ✓ Done  │  │                │                 │
│ 4  Cutting out items  In progress│  │[/ ₹1,200     ] │{/ ! Add price } │
│    ━━━━━━━━━━━━━━━──────────     │  │ Blue silk      │ Cotton print    │
│ 5  Matching prices               │  │ saree          │ saree           │
│ 6  Writing details               │  │ AI background  │ AI background   │
│ 7  Checking for mistakes         │  ├────────────────┼─────────────────┤
│ 8  Making clean photos           │  │     photo      │     photo       │
├──────────────────────────────────┤  │[/ ₹850       ] │{/ ! ₹1,200 or}  │
│ You can close the app. Your      │  │                │{    ₹1,000?  }  │
│ items will be here when ready.   │  │ Green cotton   │ Red bandhani    │
│ See details                      │  ├────────────────┴─────────────────┤
└──────────────────────────────────┘  │ [         Fix 3 prices         ] │
                                      └──────────────────────────────────┘
```

- Processing: the only numbered markers in the app (a real sequence). Steps 2 and 3 run in parallel. The upload
  shows first as its own bar ("Uploading 64%"). A failed step shows "!" + what went wrong, and the footer offers
  "Try again", which reruns only that step; when done the footer shows "Review items". "See details" = run log.
- Review: "Fix 3 prices" opens the edit sheet on the first open flag and steps through the rest; it reads
  "Fix 4 items" when non-price flags are open, and "Publish" when none are.

```text
PRODUCT EDIT SHEET (over review)      YOUR CATALOG (seller share)
┌──────────────────────────────────┐  ┌──────────────────────────────────┐
│  review grid under a 50% scrim   │  │ Your catalog                     │
╭──────────────────────────────────╮  │ ✓ Published 27 Oct, 4:20 pm      │
│ 1 of 3                    Close  │  │ 12 items                         │
│ ┌──────┐ Cotton print saree      │  │ shop.example/s/sharma-sarees     │
│ │photo │ AI-edited background.   │  │ [ Copy link ]                    │
│ │      │ Product photo is real.  │  ├──────────────────────────────────┤
│ └──────┘                         │  │ For Instagram and WhatsApp shops │
│ Heard "barah sau" at 0:21        │  │ Download feed file (CSV)         │
│ Tag shows ₹1,000 at 0:23         │  │ Upload it once in Commerce       │
│ Price                            │  │ Manager. How to do it            │
│ ┌──────────────────────────────┐ │  │ Download photos (ZIP)            │
│ │ ₹ 1,200                      │ │  ├──────────────────────────────────┤
│ └──────────────────────────────┘ │  │ Record new stock                 │
│ [ ₹1,200 heard ] [ ₹1,000 tag ]  │  │ See details                      │
│ Edit title and details           │  │                                  │
│ Remove item                      │  │                                  │
├──────────────────────────────────┤  ├──────────────────────────────────┤
│ [             Save             ] │  │ [      Share on WhatsApp       ] │
└──────────────────────────────────┘  └──────────────────────────────────┘
```

- Edit sheet: each evidence line opens the frame at that time; quick-pick buttons fill the price field
  (`inputmode="numeric"`, 29/700 tabular); "Remove item" is `rule` text and asks first; "1 of 3" is a position
  counter, not a step marker.
- Catalog: "Share on WhatsApp" uses `navigator.share`, falling back to `https://wa.me/?text=`; downloads are
  short-lived signed URLs fetched on tap.

```text
PUBLIC SHOP  /s/sharma-sarees         SETTINGS
┌──────────────────────────────────┐  ┌──────────────────────────────────┐
│ Sharma Sarees                    │  │ Settings                         │
│ 12 items                         │  ├──────────────────────────────────┤
│                 English | Hindi  │  │ Shop                             │
├──────────────────────────────────┤  │ Shop name                        │
│ ┃ ┌──────┐ Blue silk saree       │  │ [ Sharma Sarees               ]  │
│ ┃ │photo │ ₹1,200                │  │ WhatsApp number                  │
│ ┃ │      │ AI-edited             │  │ [ +91 98765 43210             ]  │
│ ┃ └──────┘ background            │  │ Language                         │
│ ┃ [    Order on WhatsApp     ]   │  │ ( English )( Hindi )             │
│ ┃ ────────────────────────────── │  │ [x] Mark AI backgrounds on       │
│ ┃ ┌──────┐ Cotton print saree    │  │     photos                       │
│ ┃ │photo │ ₹850                  │  │ Your data                        │
│ ┃ │      │                       │  │ Delete videos after [ 7 days v ] │
│ ┃ └──────┘                       │  │ Download my data                 │
│ ┃ [    Order on WhatsApp     ]   │  │ Signed-in phones (2)             │
│ ┃ ────────────────────────────── │  │ Delete account                   │
│ ┃ Prices and stock are set by    │  ├──────────────────────────────────┤
│ ┃ Sharma Sarees.                 │  │ [             Save             ] │
└──────────────────────────────────┘  └──────────────────────────────────┘
```

- Public shop: `sheet` page, rows split by 1 px `ink-2` rules, a 2 px `rule` margin line 16 px from the left edge
  down the whole list. Photo 96 × 96, title strong, price 29/700 tabular. "Order on WhatsApp" is an outline button
  opening `https://wa.me/<digits>?text=<encoded>` ("Hello Sharma Sarees, I want to order Blue silk saree
  (₹1,200). Item code S7K2."). Only approved fields: no seller email, internal IDs or video. The language switch
  shows each name in its own script, "English" and "हिन्दी".
- Settings: plain labelled fields, no row chevrons. "Delete account" is `rule` text and opens a sheet that asks
  for the shop name to be typed. Integration keys and webhooks appear only when `APP_MODE=socialpulse`.

```text
CAMERA BLOCKED              NO CAMERA                   NOT A SECURE LINK
┌────────────────────────┐  ┌────────────────────────┐  ┌────────────────────────┐
│ Camera is blocked      │  │ No camera found        │  │ Camera needs https     │
│ Tap the lock next to   │  │ This phone or browser  │  │ Open this link in      │
│ the web address.       │  │ gave no camera. Record │  │ Chrome:                │
│ Allow Camera and       │  │ with the camera app,   │  │ https://shop.example   │
│ Microphone.            │  │ then upload the video. │  │ [ Copy link ]          │
│ Then tap Try again.    │  │                        │  │                        │
├────────────────────────┤  ├────────────────────────┤  ├────────────────────────┤
│ [     Try again      ] │  │ [Upload from gallery ] │  │ [Upload from gallery ] │
└────────────────────────┘  └────────────────────────┘  └────────────────────────┘
```

- Fix steps are plain lines without numbers (an `<ol>` with no visible markers); "Upload from gallery" is the fallback.

## 8. Copy

- Plain words a shop owner uses: "item", "price", "photo", "your catalog". Not "SKU", "asset", "job", "pipeline".
- Sentence case everywhere; active verbs on every button; no `text-transform: uppercase` (a CI grep fails on it).
- The same action keeps the same name on every screen, in notifications, in docs and in the Phoenix review link.
- Say what the assistant did, in numbers: "Found 12 items. 3 prices need a check." Never "magic", "smart",
  "AI-powered", "instantly", "effortless". The only AI wording is the factual "AI-edited background" label.
- Errors say what happened and what to do next. Never "Sorry", "Oops" or "Something went wrong".
- No emoji (an i18n test fails on any `\p{Extended_Pictographic}` in `en.json` or `hi.json`).
- Hindi is natural Hindi with common loanwords (वीडियो, फ़ोटो, लिंक), not a word-by-word translation.

| Action (key) | English | Hindi |
|---|---|---|
| `record` | Record | रिकॉर्ड करें |
| `stop` | Stop | रोकें |
| `use_video` | Use this video | यही वीडियो लें |
| `retake` | Retake | दोबारा रिकॉर्ड करें |
| `upload_gallery` | Upload from gallery | गैलरी से अपलोड करें |
| `fix_prices` | Fix 3 prices | 3 दाम ठीक करें |
| `save` | Save | सेव करें |
| `publish` | Publish | पब्लिश करें |
| `share_whatsapp` | Share on WhatsApp | WhatsApp पर भेजें |
| `order_whatsapp` | Order on WhatsApp | WhatsApp पर ऑर्डर करें |
| `try_again` | Try again | फिर से कोशिश करें |
| `send_code` | Send code | कोड भेजें |

Status lines:
- "Found 12 items. 3 prices need a check." / "12 सामान मिले। 3 दाम जाँचने हैं।"
- "You can close the app. Your items will be here when ready." / "आप ऐप बंद कर सकते हैं। सामान तैयार होते ही यहाँ दिखेंगे।"
- "AI-edited background. Product photo is real." / "बैकग्राउंड AI से बदला गया है। सामान की फ़ोटो असली है।"

| Error | English | Hindi |
|---|---|---|
| Upload interrupted | Upload stopped at 64%. The video is still on this phone. Turn on the internet and tap Try again. | अपलोड 64% पर रुक गया। वीडियो इसी फ़ोन में है। इंटरनेट चालू करें और "फिर से कोशिश करें" दबाएँ। |
| Video too long | This video is 2 min 10 s. Videos can be up to 60 seconds. Record again or pick a shorter video. | यह वीडियो 2 मिनट 10 सेकंड का है। वीडियो 60 सेकंड तक का हो सकता है। दोबारा रिकॉर्ड करें या छोटा वीडियो चुनें। |
| No prices heard | No prices were heard; the sound is too quiet. Type the prices on the next screen, or record again closer to the stock. | कोई दाम सुनाई नहीं दिया, आवाज़ बहुत धीमी है। अगली स्क्रीन पर दाम लिखें, या सामान के पास से दोबारा रिकॉर्ड करें। |
| Daily limit reached | Your shop has used today's processing limit. The video is saved. Tap Try again tomorrow. | आपकी दुकान की आज की सीमा पूरी हो गई है। वीडियो सेव है। कल "फिर से कोशिश करें" दबाएँ। |

## 9. Motion

Motion appears only in response to a user action or to show pipeline progress. At most 200 ms, `transform` and
`opacity` only (cheap on a 2 GB phone), no animation library.

| Animation | Trigger | Behaviour | Under `prefers-reduced-motion: reduce` |
|---|---|---|---|
| Recording dot pulse | Seller taps Record | `●` pulses at 1 Hz while recording | Steady dot; the word "Recording" carries the state |
| Upload progress fill | Upload running | Bar follows bytes sent, 200 ms linear | Bar jumps to each new value |
| Pipeline step advance | A step finishes | Icon swaps to a check, 150 ms; running step shows a sliding 2 px bar | Static "In progress" text, no sliding bar |
| Bottom sheet | Tap a tile or Fix prices | Slides up 200 ms ease-out, scrim fades in | Appears instantly |

Not allowed: page transitions, fade or slide on scroll or mount, skeleton shimmer, celebration effects on
publish, parallax, hover-only effects. Under reduced motion a global rule sets `animation: none` and
`transition: none` on everything; live readouts (countdown, mic segments, upload %) still update, with no easing.

## 10. Accessibility and performance floor

- **Width**: works from 320 px with no horizontal scroll; 2-column Review grid down to 320 px; reflows at 200% text.
- **Contrast**: section 3, prices AAA; meaning is never colour alone.
- **Focus**: visible ring everywhere (section 5); logical order; the bottom sheet traps focus, closes on Escape
  and returns focus to the tile that opened it.
- **Language**: the switch sets `<html lang="hi">` or `lang="en"` (driving the `:lang(hi)` scale and screen-reader
  pronunciation) and is saved to the account. Product titles carry their own `lang` attribute.
- **Screen-reader labels** (i18n keys, both languages):
  - Record button: "Record" / "रिकॉर्ड करें", then "Stop recording" / "रिकॉर्डिंग रोकें". The countdown is a silent
    `role="timer"`; a polite live region says "30 seconds left", "10 seconds left", "Recording stopped".
  - Price tag tile: "Blue silk saree. Price ₹1,200." / "Cotton print saree. Price missing. Needs a check." The
    screen-reader pass confirms TalkBack reads ₹ as rupees; if not, the label spells out "rupees".
  - Mic meter: `role="meter"`, `aria-label="Microphone level"`, values 0–100, `aria-valuetext` = the visible word.
  - Torch: `<button aria-pressed>` "Torch". Processing steps are an `<ol>`; status icons carry hidden text.
- **2 GB RAM Android**: initial seller route at most 150 KB JS gzip; public shop a separate chunk of at most 80 KB
  with no recorder code (CI-checked). woff2 subsets only (static 400/600/700 if variable files exceed budget).
  320 px thumbnails, `srcset`, `loading="lazy"`, fixed size. MediaRecorder writes 1 s chunks straight to IndexedDB,
  never one blob in React state; no canvas work on the feed; mic meter samples an `AnalyserNode` (`fftSize` 256) at
  about 10 Hz; tracks stop and object URLs are revoked on leaving. No `backdrop-filter` or animated SVG.

## 11. Review against the avoid list

| Avoid item (brief, section 7) | Status in this plan |
|---|---|
| Cream background + serif display + terracotta accent | Clear. Cool grey `ledger` + white `sheet`, Noto Sans only, accents `pen` blue and `tag` yellow (change 1) |
| Near-black background + one neon accent | Clear. Light theme; the record screen's `ink` panels hold white text and a red record disc, no neon |
| Identical rounded cards with the same soft shadow | Clear. 0-radius tiles with 1 px rules, notched tags, ledger rows; one shadow, on the sheet (change 3) |
| Gradient washes | Clear. Flat fills only; the scrim is flat 50% `ink` |
| Glassmorphism | Clear. No `backdrop-filter`; guidance chips over the camera are solid `ink` |
| ALL-CAPS tracked eyebrow labels | Clear. Section labels are sentence-case title text; uppercase blocked in CSS (change 5) |
| "A · B · C" meta strings | Clear after change 7 (the approved Review header was "12 items · Fix 3 prices") |
| "→" on every button | Clear. Buttons are words only; no chevrons on Settings rows either (change 5) |
| One highlighted word in a headline | Clear. Headings are one colour, `ink` |
| Numbered markers without a true sequence | Clear. Only the processing steps are numbered (change 4); camera fix steps are unnumbered |
| Sparkle icons and "AI magic" language | Clear. No sparkles; copy states results; the AI label is a factual disclosure (change 5) |
| Fade-and-slide-up on every section | Clear. Section 9 lists the only four animations |
| Emoji in UI copy | Clear. Blocked by the i18n test; the torch is an SVG icon plus a word, not a glyph |

Changes recorded in the approved plan:
1. Cream "ledger paper" background → cool grey `ledger` + white `sheet`: avoids cream/serif/terracotta and reads
   better in sunlight.
2. Ledger red as the primary button → primary is `pen` blue; red stays for rules and errors, so red means "look here".
3. Identical rounded shadow cards on Review → photo + notched price tag, 0-radius tiles split by 1 px rules, no
   shadows. The public page uses ledger rows, not cards.
4. Numbered markers only in the pipeline progress, a true sequence.
5. No eyebrow labels, "→" on buttons, sparkle icons or "AI magic" copy: the assistant is described by what it did.
6. Boldness spent once: yellow tags and 40 px prices on Review; everything else is ink on white.

Further changes made in this document:
7. Review header "12 items · Fix 3 prices" (a "·" meta string) → "Found 12 items" / "3 prices need a check.";
   "Fix 3 prices" is only the footer button.
8. Record screen: `pen` on `ink` measured 1.99:1 → white focus ring there (17.82:1); the red disc on `ink`
   measured 2.73:1 → it sits inside a white ring.
9. `ok` green set to #1B6E3A (6.29:1 on `sheet`, 5.50:1 on `ledger`), always with an icon and words.
10. "Needs a check" was "?" on a yellow tag → blank white tag, red outline, "!" icon and words (reads in greyscale).
11. Torch moved from top-right to the bottom strip (thumb reach); SVG icon + "Torch" instead of a lightning glyph.
12. Processing steps reordered to match the pipeline (finding items and hearing prices run together).
13. Public "Order on WhatsApp" buttons are outline, so a long list is not a column of blue blocks.
14. 1 px rules use `ink-2` (8.20:1) instead of a new light-grey token, because light rules vanish in sunlight.

## 12. Screenshot plan

UI work is not done until each screen has been captured at 360 × 800 and critiqued in writing.

- Playwright (`PROVIDERS=fake`, 360 × 800, `deviceScaleFactor: 2`), English and Hindi, saved as
  `docs/screenshots/<screen>-<state>-<lang>.png` (also used by the README).
- States: sign in (email, code, wrong code); consent (account, recording); record (idle, recording, 10 s left,
  preview, denied, no camera, insecure); processing (uploading, running, failed, done); review (flags, all
  confirmed); edit sheet (missing, conflict); catalog; public shop; settings (default, delete confirmation).
- Extra passes: 320 × 640 (overflow, long Hindi, ₹1,20,000 on a tag), greyscale, 200% text, keyboard-only focus,
  axe-core with zero serious violations.
- Each critique checks: one primary action in the thumb zone; prices are the largest figures; nothing from the
  avoid list; no clipped Devanagari; copy follows section 8. Every problem is fixed or logged in PROGRESS.md.
- One check on a real budget Android phone outdoors: are prices and the primary button readable at arm's length?
