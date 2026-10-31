import { useEffect, useRef, useState, type CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { Icon, type IconName } from "../components/Icon";
import { Signboard } from "../components/Signboard";
import { formatINR } from "../format";
import { useSession } from "../session";
import { LanguageButton } from "../Shell";
import { useStartShop } from "./SignIn";

const SOURCE = "https://github.com/manikantpandey/shelf-to-shop";
const DOCS = `${SOURCE}/blob/main`;
/** From evals/report.md (run of Oct 29, 2026). Change both together. */
export const EVALS = { videos: 4, real: 3, items: 21, found: 21, wrong: 0, asked: 3, minutes: 26 };
const STEPS = ["record", "check", "share"] as const;
const STEP_MS = 5200;
/** Real photos from the sample shop, which was made from the seller's own 24-second clip. */
const ITEMS = [
  { key: "nutcracker", price: 4, mrp: 0 },
  { key: "peanuts", price: 4, mrp: 0 },
  { key: "tadka", price: 4, mrp: 5 },
] as const;

const at = (i: number) => ({ "--i": i }) as CSSProperties;

function useStill(): boolean {
  const [still] = useState(() => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false);
  return still;
}

/** One phone screen of the demo. Remounted per step, so its entrance plays each time it is shown. */
function Screen({ step }: { step: number }) {
  const { t } = useTranslation();
  const name = (key: string) => t(`landing.demo.${key}`);

  if (step === 0) {
    const words = t("landing.demo.said").split(" ");
    return (
      <div className="scr rec">
        <img src="/landing/shelf.jpg" alt="" width={478} height={850} />
        <span className="rec-time">0:19</span>
        <span className="focus"><span>{name("tadka")}</span></span>
        <div className="said">
          <p lang="hi-Latn">{words.map((w, i) => <span key={i} style={at(i)}>{w} </span>)}</p>
          <span className="m-heard"><span className="pricetag">{formatINR(4)}</span>{t("landing.demo.heard", { time: "0:19" })}</span>
        </div>
      </div>
    );
  }

  if (step === 1) {
    return (
      <div className="scr rev">
        <p className="m-bar">{t("review.found", { count: ITEMS.length })}</p>
        <div className="mini-tiles">
          {ITEMS.map((it, i) => (
            <span key={it.key} className={`mini-tile${it.mrp ? " picked" : ""}`} style={at(i)}>
              <span className="ph">
                <img src={`/landing/${it.key}.jpg`} alt="" width={400} height={400} />
                <span className="pricetag">{formatINR(it.price)}</span>
              </span>
              <span className="nm">{name(it.key)}</span>
              <span className="mm">{it.mrp ? <>{t("shop.mrp")} <s>{formatINR(it.mrp)}</s></> : " "}</span>
            </span>
          ))}
        </div>
        <p className="proof-card"><span className="t">0:19</span><span>{t("landing.demo.evidence")}</span></p>
        <span className="m-btn">{t("review.publish")}</span>
      </div>
    );
  }

  const inBasket = ITEMS.filter((it) => it.key !== "peanuts");
  const total = inBasket.reduce((sum, it) => sum + it.price, 0);
  return (
    <div className="scr shopview">
      <p className="mini-board"><span>{t("landing.demo.shop_name")}</span></p>
      <div className="mini-tiles">
        {ITEMS.map((it, i) => (
          <span key={it.key} className="mini-tile" style={at(i)}>
            <span className="ph">
              <img src={`/landing/${it.key}.jpg`} alt="" width={400} height={400} />
              <span className="pricetag">{formatINR(it.price)}</span>
            </span>
            <span className="nm">{name(it.key)}</span>
            <span className="m-act">
              <span className="add">{t("shop.add")}</span>
              {it.key !== "peanuts" ? <span className="qty" style={at(i)}><span>−</span>1<span>+</span></span> : null}
            </span>
          </span>
        ))}
      </div>
      <span className="m-basket">
        <span>{t("shop.items_count", { count: inBasket.length })}</span>
        <span>{t("shop.view_basket", { total: formatINR(total) })}</span>
      </span>
      <div className="bubble">
        <span className="wa-label">{t("landing.wa.app")}</span>
        <strong>{t("landing.demo.order_head", { shop: t("landing.demo.shop_name"), number: 12 })}</strong>
        {inBasket.map((it) => <span key={it.key}>{t("landing.demo.order_line", { item: name(it.key), price: formatINR(it.price) })}</span>)}
        <strong>{t("landing.demo.order_total", { total: formatINR(total) })}</strong>
        <span className="wa-time">10:42 <Icon name="check2" size={13} /></span>
      </div>
    </div>
  );
}

/** Record, check, share: plays once when it comes on screen and stops on the shop; tap a step to see it. */
function Demo() {
  const { t } = useTranslation();
  const still = useStill();
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(false);
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (still || !el || typeof IntersectionObserver === "undefined") return;
    const seen = new IntersectionObserver(
      (entries) => {
        if (!entries.some((e) => e.isIntersecting)) return;
        setPlaying(true);
        seen.disconnect();
      },
      { threshold: 0.4 },
    );
    seen.observe(el);
    return () => seen.disconnect();
  }, [still]);

  useEffect(() => {
    if (!playing) return;
    const timer = window.setTimeout(() => {
      if (step < STEPS.length - 1) setStep(step + 1);
      else setPlaying(false);
    }, STEP_MS);
    return () => window.clearTimeout(timer);
  }, [playing, step]);

  const last = step === STEPS.length - 1;
  const control: [IconName, string, () => void] = playing
    ? ["pause", t("landing.pause"), () => setPlaying(false)]
    : last
      ? ["replay", t("landing.replay"), () => { setStep(0); setPlaying(true); }]
      : ["play", t("landing.play"), () => setPlaying(true)];

  return (
    <figure className="demo" ref={ref} aria-labelledby="demo-say">
      <div className="phone" aria-hidden="true">
        <div className="screen">
          <Screen key={step} step={step} />
        </div>
      </div>
      <div className="demo-steps" role="group" aria-label={t("landing.demo_label")}>
        {STEPS.map((s, i) => (
          <button key={s} type="button" aria-pressed={step === i} className={playing && step === i ? "timing" : undefined}
            style={{ "--step-ms": `${STEP_MS}ms` } as CSSProperties}
            onClick={() => { setStep(i); setPlaying(false); }}>
            <span className="n">{i + 1}</span> {t(`landing.step.${s}`)}
          </button>
        ))}
      </div>
      <figcaption className="demo-say">
        <button type="button" className="icon-btn" onClick={control[2]} aria-label={control[1]}>
          <Icon name={control[0]} />
        </button>
        <span id="demo-say" aria-live="polite">{t(`landing.step_text.${STEPS[step]}`)}</span>
      </figcaption>
    </figure>
  );
}

const ORDER = [
  { key: "nutcracker", qty: 1, price: 4 },
  { key: "slice", qty: 2, price: 20 },
  { key: "tadka", qty: 3, price: 4 },
] as const;

function WhatsAppChat() {
  const { t } = useTranslation();
  const total = ORDER.reduce((sum, l) => sum + l.qty * l.price, 0);
  return (
    <figure className="wa-chat" aria-labelledby="wa-chat-cap">
      <div className="wa-phone" aria-hidden="true">
        <div className="wa-head">
          <Icon name="back" size={18} />
          <span className="wa-avatar">{t("landing.wa.customer").slice(0, 1)}</span>
          <span className="wa-who"><strong>{t("landing.wa.customer")}</strong><small>{t("landing.wa.online")}</small></span>
        </div>
        <div className="wa-body">
          <span className="wa-day">{t("landing.wa.today")}</span>
          <div className="wa-msg in">
            <strong>{t("landing.demo.order_head", { shop: t("landing.demo.shop_name"), number: 12 })}</strong>
            {ORDER.map((l) => (
              <span key={l.key}>{t("landing.wa.line", { qty: l.qty, item: t(`landing.wa.item_${l.key}`), cost: formatINR(l.qty * l.price) })}</span>
            ))}
            <strong>{t("landing.demo.order_total", { total: formatINR(total) })}</strong>
            <span>{t("landing.wa.name", { name: t("landing.wa.customer") })}</span>
            <span>{t("landing.wa.note")}</span>
            <span className="wa-link">{t("landing.wa.shop_page")}</span>
            <span className="wa-time">10:42</span>
          </div>
          <div className="wa-msg out">
            <span>{t("landing.wa.reply")}</span>
            <span className="wa-time">10:43 <Icon name="check2" size={13} /></span>
          </div>
        </div>
        <div className="wa-input"><span>{t("landing.wa.type")}</span></div>
      </div>
      <figcaption id="wa-chat-cap" className="muted small">{t("landing.wa.caption")}</figcaption>
    </figure>
  );
}

/** What one video gives the shop, printed like the slip from a billing machine. */
function Receipt() {
  const { t } = useTranslation();
  const lines: [string, string][] = [
    [t("landing.r.page"), "1"],
    [t("landing.r.feed"), "1"],
    [t("landing.r.photos"), String(ITEMS.length)],
    [t("landing.r.orders"), "1"],
    [t("landing.r.poster"), "1"],
  ];
  const sum: [string, string][] = [
    [t("landing.r.typing"), t("landing.r.none")],
    [t("landing.r.time"), t("landing.r.minutes")],
  ];
  const row = ([what, value]: [string, string]) => (
    <li key={what}><span>{what}</span><span className="dots" /><span className="num">{value}</span></li>
  );
  return (
    <div className="receipt">
      <p className="r-head">{t("app.name")}</p>
      <p className="r-sub">{t("landing.r.from")}</p>
      <ul className="r-lines">{lines.map(row)}</ul>
      <ul className="r-lines r-sum">{sum.map(row)}</ul>
    </div>
  );
}

const FEATURES: [string, IconName][] = [
  ["record", "record"], ["found", "items"], ["photos", "camera"], ["questions", "alert"],
  ["page", "store"], ["orders", "chat"], ["book", "orders"], ["stock", "sections"],
  ["feed", "download"], ["offers", "tag"], ["lang", "lang"], ["privacy", "shield"],
];
const HERO_FACTS: [string, IconName][] = [["whatsapp", "chat"], ["lang", "lang"], ["approve", "shield"]];

/** The front door at `/`: what the app does, the proof, and the two ways in (or back to your shop). */
export function Landing() {
  const { t } = useTranslation();
  const { me } = useSession();
  const { signIn, busy, error } = useStartShop();

  const sample = () => void signIn({ sample: true }, "sample");
  const sampleLabel = busy === "sample" ? t("signin.opening") : t("signin.sample");
  const link = (href: string, label: string) => <a href={href} target="_blank" rel="noopener">{label}</a>;

  return (
    <div className="front">
      <header className="front-top">
        <Signboard name={t("app.name")} compact as="p" />
        <LanguageButton />
      </header>
      <main>
        <section className="front-hero" aria-labelledby="hero-h">
          <div className="hero-copy">
            <h1 id="hero-h">{t("landing.title")}</h1>
            <p className="lead">{t("landing.lead")}</p>
            <div className="hero-acts">
              {me ? (
                <Link className="btn primary big" to="/home">{t("landing.open_shop")}</Link>
              ) : (
                <button type="button" className="btn primary big" onClick={sample} disabled={busy !== ""}>{sampleLabel}</button>
              )}
              <Link className="btn big" to="/signin">{t("landing.own")}</Link>
            </div>
            {error ? <p className="error" role="alert">{error}</p> : null}
            <ul className="hero-facts">
              {HERO_FACTS.map(([key, icon]) => (
                <li key={key}><Icon name={icon} size={20} />{t(`landing.fact.${key}`)}</li>
              ))}
            </ul>
          </div>
          <div className="hero-visual">
            {/* Three real items from the sample shop, as tagged tiles around the phone (laptops only). */}
            <div className="float-tiles" aria-hidden="true">
              {ITEMS.map((it) => (
                <span key={it.key} className={`float-tile f-${it.key}`}>
                  <img src={`/landing/${it.key}.jpg`} alt="" width={400} height={400} />
                  <span className="pricetag">{formatINR(it.price)}</span>
                </span>
              ))}
            </div>
            <Demo />
          </div>
        </section>

        <section className="band wa alt" aria-labelledby="wa-h">
          <div className="stack">
            <h2 id="wa-h">{t("landing.wa.title")}</h2>
            <p className="lead">{t("landing.wa.lead")}</p>
            <ol className="wa-steps">
              <li>{t("landing.wa.step_1")}</li>
              <li>{t("landing.wa.step_2")}</li>
              <li>{t("landing.wa.step_3")}</li>
            </ol>
            <p className="wa-offers"><Icon name="tag" size={20} />{t("landing.wa.offers")}</p>
            <p className="muted">{t("landing.wa.catalog")}</p>
          </div>
          <WhatsAppChat />
        </section>

        <section className="band features" aria-labelledby="features-h">
          <h2 id="features-h">{t("landing.features_title")}</h2>
          <p className="lead">{t("landing.features_lead")}</p>
          <ul className="feature-grid">
            {FEATURES.map(([key, icon]) => (
              <li key={key}>
                <span className="ic"><Icon name={icon} /></span>
                <h3>{t(`landing.feature.${key}`)}</h3>
                <p className="muted">{t(`landing.feature.${key}_text`)}</p>
              </li>
            ))}
          </ul>
        </section>

        <section className="band get tinted" aria-labelledby="get-h">
          <div className="stack">
            <h2 id="get-h">{t("landing.get_title")}</h2>
            <p className="lead">{t("landing.get_lead")}</p>
            <p className="muted">{t("landing.feed_note")}</p>
          </div>
          <Receipt />
        </section>

        <section className="band proof alt" aria-labelledby="proof-h">
          <h2 id="proof-h">{t("landing.proof_title")}</h2>
          <p className="lead">{t("landing.proof_lead", { videos: EVALS.videos, real: EVALS.real, items: EVALS.items })}</p>
          <ul className="proof-figs">
            <li><span className="num">{t("landing.fig.found", { found: EVALS.found, items: EVALS.items })}</span><span>{t("landing.fig.found_label")}</span></li>
            <li><span className="num">{EVALS.wrong}</span><span>{t("landing.fig.wrong_label")}</span></li>
            <li><span className="num">{EVALS.asked}</span><span>{t("landing.fig.asked_label")}</span></li>
            <li><span className="num">{t("landing.fig.minutes", { minutes: EVALS.minutes })}</span><span>{t("landing.fig.minutes_label")}</span></li>
          </ul>
          <p>{t("landing.proof_body")}</p>
          <p>{link(`${DOCS}/evals/report.md`, t("landing.proof_link"))}</p>
        </section>


      </main>

      <footer className="front-foot dark">
        <div className="foot-cta">
          <p className="foot-line">{t("landing.footer_cta")}</p>
          {me ? (
            <Link className="btn record-btn big" to="/home">{t("landing.open_shop")}</Link>
          ) : (
            <button type="button" className="btn record-btn big" onClick={sample} disabled={busy !== ""}>{sampleLabel}</button>
          )}
        </div>
        <nav className="foot-links" aria-label={t("landing.footer_nav")}>
          <div>
            <h2>{t("landing.use")}</h2>
            <ul>
              <li><button type="button" onClick={sample} disabled={busy !== ""}>{t("signin.sample")}</button></li>
              <li><Link to="/signin">{t("landing.own")}</Link></li>
            </ul>
          </div>
          <div>
            <h2>{t("landing.open_source")}</h2>
            <ul>
              <li>{link(SOURCE, t("landing.source"))}</li>
              <li>{link(`${DOCS}/evals/report.md`, t("landing.tests"))}</li>
              <li>{link(`${DOCS}/docs/privacy.md`, t("landing.privacy"))}</li>
              <li>{link(`${DOCS}/docs/security.md`, t("landing.security"))}</li>
            </ul>
          </div>
        </nav>
        <p className="foot-board" aria-hidden="true"><span>{t("app.name")}</span></p>
        <p className="foot-small">{t("landing.built")}</p>
      </footer>
    </div>
  );
}
