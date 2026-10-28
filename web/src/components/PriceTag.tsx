import { formatINR } from "../format";

/** Hang-tag price: marigold fill, notched edge, tabular figures. */
export function PriceTag({ value, size = "md", stamp = false }: { value: number; size?: "md" | "lg"; stamp?: boolean }) {
  return <span className={`pricetag ${size}${stamp ? " stamp" : ""}`}>{formatINR(value)}</span>;
}
