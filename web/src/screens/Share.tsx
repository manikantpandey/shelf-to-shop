import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api, type MyCatalog, type PublicProduct, type PublicShop } from "../api";
import { Icon } from "../components/Icon";
import { useSession } from "../session";
import { Shell } from "../Shell";

const W = 1080;
const H = 1920;
const INK = "#17201c";
const BOARD = "#0f4c3a";
const MARIGOLD = "#f6b526";

export async function qrDataUrl(url: string, width = 600): Promise<string> {
  return QRCode.toDataURL(url, { margin: 1, width, color: { dark: INK, light: "#ffffff" } });
}

async function loadImage(src: string): Promise<ImageBitmap> {
  // Fetched as data, so the picture never taints the canvas (it can then be saved).
  const res = await fetch(src);
  return createImageBitmap(await res.blob());
}

function wrap(ctx: CanvasRenderingContext2D, text: string, maxWidth: number): string[] {
  const words = text.split(/\s+/);
  const lines: string[] = [];
  let line = "";
  for (const word of words) {
    const next = line ? `${line} ${word}` : word;
    if (ctx.measureText(next).width > maxWidth && line) {
      lines.push(line);
      line = word;
    } else {
      line = next;
    }
  }
  if (line) lines.push(line);
  return lines.slice(0, 3);
}

/** A 1080x1920 WhatsApp Status picture: the shop's board, one item, its price tag, the link. */
async function statusImage(shopName: string, url: string, item: PublicProduct, hindi: boolean, cta: string): Promise<Blob> {
  await document.fonts.ready;
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = BOARD;
  ctx.fillRect(0, 0, W, H);
  // Signboard
  ctx.strokeStyle = MARIGOLD;
  ctx.lineWidth = 6;
  ctx.strokeRect(60, 80, W - 120, 200);
  ctx.fillStyle = MARIGOLD;
  ctx.textAlign = "center";
  ctx.font = "700 68px Poppins, sans-serif";
  const nameLines = wrap(ctx, shopName.toUpperCase(), W - 200);
  nameLines.slice(0, 2).forEach((l, i) => ctx.fillText(l, W / 2, 170 + i * 76 - (nameLines.length > 1 ? 30 : 0)));
  // Photo card
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(60, 340, W - 120, W - 120);
  const photo = await loadImage(item.image_url);
  ctx.drawImage(photo, 60, 340, W - 120, W - 120);
  // Price tag with a notch
  const price = item.price_display;
  ctx.font = "700 96px Poppins, sans-serif";
  const tagW = ctx.measureText(price).width + 110;
  const tagY = 340 + W - 120 - 170;
  ctx.fillStyle = MARIGOLD;
  ctx.beginPath();
  ctx.moveTo(60 + 40, tagY);
  ctx.lineTo(60 + tagW, tagY);
  ctx.lineTo(60 + tagW, tagY + 130);
  ctx.lineTo(60 + 40, tagY + 130);
  ctx.lineTo(60, tagY + 65);
  ctx.closePath();
  ctx.fill();
  ctx.fillStyle = INK;
  ctx.textAlign = "left";
  ctx.fillText(price, 60 + 70, tagY + 100);
  // Title and MRP
  ctx.fillStyle = "#ffffff";
  ctx.textAlign = "center";
  ctx.font = "600 60px Poppins, sans-serif";
  const titleLines = wrap(ctx, hindi ? item.title_hi : item.title_en, W - 160);
  titleLines.forEach((l, i) => ctx.fillText(l, W / 2, 1420 + i * 76));
  if (item.mrp_display) {
    ctx.font = "500 44px Poppins, sans-serif";
    ctx.fillStyle = "rgba(255,255,255,0.75)";
    const mrp = `MRP ${item.mrp_display}`;
    const y = 1420 + titleLines.length * 76 + 10;
    ctx.fillText(mrp, W / 2, y);
    const half = ctx.measureText(mrp).width / 2;
    ctx.fillRect(W / 2 - half, y - 15, half * 2, 4);
  }
  // Call to action with a QR code
  const qr = await loadImage(await qrDataUrl(url, 300));
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(60, 1640, 220, 220);
  ctx.drawImage(qr, 70, 1650, 200, 200);
  ctx.textAlign = "left";
  ctx.fillStyle = MARIGOLD;
  ctx.font = "700 48px Poppins, sans-serif";
  ctx.fillText(cta, 320, 1730);
  ctx.fillStyle = "#ffffff";
  ctx.font = "500 34px Poppins, sans-serif";
  wrap(ctx, url.replace(/^https?:\/\//, ""), W - 380).forEach((l, i) => ctx.fillText(l, 320, 1790 + i * 44));
  return new Promise((resolve) => canvas.toBlob((b) => resolve(b!), "image/png"));
}

export function Share() {
  const { t, i18n } = useTranslation();
  const { me } = useSession();
  const [catalog, setCatalog] = useState<MyCatalog | null>(null);
  const [shop, setShop] = useState<PublicShop | null>(null);
  const [qr, setQr] = useState("");
  const [picked, setPicked] = useState("");
  const [preview, setPreview] = useState<{ url: string; blob: Blob } | null>(null);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api<MyCatalog>("/api/v1/catalog")
      .then(async (c) => {
        setCatalog(c);
        if (!c.published || !me) return;
        setQr(await qrDataUrl(c.url));
        const s = await api<PublicShop>(`/api/v1/public/shops/${me.workspace.slug}`);
        setShop(s);
        setPicked(s.products.find((p) => !p.sold_out)?.id ?? "");
      })
      .catch(() => setError(t("app.offline")));
  }, [me, t]);

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview.url);
  }, [preview]);

  if (!catalog) {
    return <Shell title={t("share.title")} back="/more">{error ? <p className="error">{error}</p> : <p className="muted">{t("app.loading")}</p>}</Shell>;
  }
  if (!catalog.published) {
    return (
      <Shell title={t("share.title")} back="/more">
        <div className="panel"><p>{t("share.not_live")}</p><Link className="btn record-btn" to="/record"><Icon name="record" />{t("nav.record")}</Link></div>
      </Shell>
    );
  }

  const hindi = i18n.language === "hi";
  const wa = `https://wa.me/?text=${encodeURIComponent(t("home.share_text", { url: catalog.url }))}`;
  const item = shop?.products.find((p) => p.id === picked);

  const makeStatus = async () => {
    if (!shop || !item) return;
    setBusy(true);
    setError("");
    try {
      const blob = await statusImage(shop.shop.name, `${catalog.url}/p/${item.id}`, item, hindi, t("share.cta"));
      setPreview({ url: URL.createObjectURL(blob), blob });
    } catch {
      setError(t("share.image_failed"));
    } finally {
      setBusy(false);
    }
  };

  const shareStatus = async () => {
    if (!preview) return;
    const file = new File([preview.blob], "status.png", { type: "image/png" });
    const nav = navigator as Navigator & { canShare?: (d: { files: File[] }) => boolean };
    if (nav.canShare?.({ files: [file] })) {
      await navigator.share({ files: [file] }).catch(() => undefined);
    } else {
      const a = document.createElement("a");
      a.href = preview.url;
      a.download = "shop-status.png";
      a.click();
    }
  };

  return (
    <Shell title={t("share.title")} back="/more">
      <section className="panel" aria-labelledby="link-h">
        <h2 id="link-h">{t("share.link")}</h2>
        <a href={catalog.url} target="_blank" rel="noopener" className="url">{catalog.url.replace(/^https?:\/\//, "")}</a>
        <div className="row">
          <a className="btn primary" href={wa} target="_blank" rel="noopener"><Icon name="chat" />{t("home.share")}</a>
          <button type="button" className="btn" onClick={async () => {
            await navigator.clipboard.writeText(catalog.url).catch(() => undefined);
            setCopied(true);
          }}>
            <Icon name={copied ? "check" : "copy"} />{copied ? t("home.copied") : t("home.copy")}
          </button>
        </div>
      </section>

      <div className="home-grid">
        <section className="panel" aria-labelledby="qr-h">
          <h2 id="qr-h">{t("share.qr")}</h2>
          <p className="muted small">{t("share.qr_hint")}</p>
          {qr ? <div className="qr"><img src={qr} alt={t("share.qr_alt")} /></div> : null}
          <div className="row">
            <Link className="btn" to="/poster" target="_blank"><Icon name="print" />{t("share.poster")}</Link>
            {qr ? <a className="btn quiet" href={qr} download="shop-qr.png"><Icon name="download" />{t("share.download_qr")}</a> : null}
          </div>
        </section>

        <section className="panel" aria-labelledby="st-h">
          <h2 id="st-h">{t("share.status")}</h2>
          <p className="muted small">{t("share.status_hint")}</p>
          <div className="field">
            <label htmlFor="st-item">{t("share.pick_item")}</label>
            <select id="st-item" className="input" value={picked} onChange={(e) => { setPicked(e.target.value); setPreview(null); }}>
              {(shop?.products ?? []).map((p) => (
                <option key={p.id} value={p.id}>{(hindi ? p.title_hi : p.title_en)} ({p.price_display})</option>
              ))}
            </select>
          </div>
          <div className="row">
            <button type="button" className="btn" onClick={makeStatus} disabled={busy || !item}>
              {busy ? t("share.making") : t("share.make")}
            </button>
            {preview ? <button type="button" className="btn primary" onClick={shareStatus}><Icon name="share" />{t("share.share_image")}</button> : null}
          </div>
          {preview ? <img className="status-preview" src={preview.url} alt={t("share.preview_alt")} /> : null}
        </section>
      </div>
      {error ? <p className="error" role="alert">{error}</p> : null}
    </Shell>
  );
}
