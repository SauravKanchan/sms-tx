export function normalizeMsisdn(raw: string): string {
  // remove everything except digits
  let n = (raw || "").replace(/\D+/g, "");

  // if it starts with India's country code (91) and has 12 digits, drop it
  if (n.length === 12 && n.startsWith("91")) n = n.slice(2);

  // trim leading zeroes (common in some forwarded formats)
  n = n.replace(/^0+/, "");

  return n;
}