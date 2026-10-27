const rupees = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

/** ₹ with Indian digit grouping: 120000 -> "₹1,20,000". */
export function formatINR(value: number): string {
  return rupees.format(value);
}

/** Stored digits "919876543210" -> "+91 98765 43210" for display; other numbers get a "+". */
export function formatPhone(digits: string | null | undefined): string {
  if (!digits) return "";
  if (digits.length === 12 && digits.startsWith("91")) return `+91 ${digits.slice(2, 7)} ${digits.slice(7)}`;
  return `+${digits}`;
}
