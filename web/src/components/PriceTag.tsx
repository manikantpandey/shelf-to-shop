import { formatINR } from "../format";

/** Hang-tag price: marigold fill, notched edge, tabular figures. */
export function PriceTag({ value, size = "md" }: { value: number; size?: "md" | "lg" }) {
  return <span className={`pricetag ${size}`}>{formatINR(value)}</span>;
}
