import { useEffect, useRef, useState, type CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { Link, Navigate } from "react-router-dom";

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
        <strong>{t("landing.demo.order_head", { shop: t("landing.demo.shop_name") })}</strong>
        {inBasket.map((it) => <span key={it.key}>{t("landing.demo.order_line", { item: name(it.key), price: formatINR(it.price) })}</span>)}
        <strong>{t("landing.demo.order_total", { total: formatINR(total) })}</strong>
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

const MADE: [string, IconName][] = [["lang", "lang"], ["phone", "phone"], ["privacy", "shield"]];

/** The front door at `/`: what the app does, the proof, and the two ways in. Signed-in sellers go Home. */
export function Landing() {
  const { t } = useTranslation();
  const { me } = useSession();
  const { signIn, busy, error } = useStartShop();
  if (me) return <Navigate to="/home" replace />;

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
              <button type="button" className="btn primary big" onClick={sample} disabled={busy !== ""}>{sampleLabel}</button>
              <Link className="btn big" to="/signin">{t("landing.own")}</Link>
            </div>
            {error ? <p className="error" role="alert">{error}</p> : null}
            <p className="muted small">{t("landing.note")}</p>
          </div>
          <Demo />
        </section>

        <section className="band get" aria-labelledby="get-h">
          <div className="stack">
            <h2 id="get-h">{t("landing.get_title")}</h2>
            <p className="lead">{t("landing.get_lead")}</p>
            <p className="muted">{t("landing.feed_note")}</p>
          </div>
          <Receipt />
        </section>

        <section className="band proof" aria-labelledby="proof-h">
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

        <section className="band made" aria-labelledby="made-h">
          <h2 id="made-h">{t("landing.made_title")}</h2>
          <ul className="made-rows">
            {MADE.map(([key, icon]) => (
              <li key={key}>
                <span className="ic"><Icon name={icon} /></span>
                <div className="stack" style={{ gap: 4 }}>
                  <h3>{t(`landing.made.${key}`)}</h3>
                  <p className="muted">{t(`landing.made.${key}_text`)}</p>
                </div>
              </li>
            ))}
          </ul>
        </section>
      </main>

      <footer className="front-foot dark">
        <div className="foot-cta">
          <p className="foot-line">{t("landing.footer_cta")}</p>
          <button type="button" className="btn record-btn big" onClick={sample} disabled={busy !== ""}>{sampleLabel}</button>
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
