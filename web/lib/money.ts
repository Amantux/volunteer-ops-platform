// Money formatting for donations. Amounts cross the wire as integer *minor
// units* (e.g. 5000 = $50.00); we never show raw minor units to a user.
//
// Integer math only: we split the whole/fraction with integer division so no
// floating-point rounding ever touches the amount. Intl is used only to derive
// the currency symbol and to group the (integer) whole part.

// A currency symbol lookup is locale-derived and stable, so cache per code.
const symbolCache = new Map<string, string>();

function currencySymbol(currency: string): string {
  const key = currency.toUpperCase();
  const cached = symbolCache.get(key);
  if (cached !== undefined) return cached;
  let symbol = key;
  try {
    const parts = new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: key,
      currencyDisplay: 'narrowSymbol',
    }).formatToParts(0);
    symbol = parts.find((p) => p.type === 'currency')?.value ?? key;
  } catch {
    // Unknown/invalid code: fall back to the raw code (e.g. "XTS").
    symbol = key;
  }
  symbolCache.set(key, symbol);
  return symbol;
}

// Format integer minor units as a currency string, e.g. formatMinor(5000, "USD")
// → "$50.00". Assumes 2 minor-unit digits (USD/GBP/EUR/CAD/AUD…), which covers
// every currency this product handles.
// Parse a human-typed major-unit amount ("50", "50.5", "$1,250.00") into integer
// minor units. Integer math only — we never multiply a float by 100. Returns
// null for anything unparseable or ≤ 0.
export function parseDollarsToMinor(input: string): number | null {
  const cleaned = input.replace(/[$,\s]/g, '');
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) return null;
  const [whole, frac = ''] = cleaned.split('.');
  const cents = `${frac}00`.slice(0, 2);
  const minor = Number(whole) * 100 + Number(cents);
  if (!Number.isSafeInteger(minor) || minor <= 0) return null;
  return minor;
}

export function formatMinor(amount: number, currency: string): string {
  const value = Math.round(amount); // defensively coerce to an integer
  const negative = value < 0;
  const abs = Math.abs(value);
  const whole = Math.trunc(abs / 100);
  const cents = abs % 100;
  const wholeStr = whole.toLocaleString('en-US');
  const body = `${wholeStr}.${String(cents).padStart(2, '0')}`;
  return `${negative ? '-' : ''}${currencySymbol(currency)}${body}`;
}
