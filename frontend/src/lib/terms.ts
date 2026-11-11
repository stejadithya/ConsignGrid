/**
 * Industry Pack vocabulary for the screens: the words people read for the stocked item, the partner holding
 * consignment stock and the partner's site. The backend is the source of truth (GET /api/config/public, from
 * backend/app/core/industry.py); `ConfigProvider` loads it once before the app renders.
 *
 * Usage inside components and functions (never in module-level constants, which are evaluated before the words
 * are loaded):
 *
 *   `${vocab.Items} sold by ${vocab.aPartner}`        // "Tyres sold by a dealer"
 *
 * Until the configuration arrives (and in unit tests) the words are the default `tyres` pack's.
 */
export const TERM_KEYS = ["item", "items", "partner", "partners", "site", "sites"] as const;
export type TermKey = (typeof TERM_KEYS)[number];
export type Words = Record<TermKey, string>;

export const DEFAULT_WORDS: Words = {
  item: "tyre", items: "tyres", partner: "dealer", partners: "dealers", site: "shop", sites: "shops",
};

const words: Words = { ...DEFAULT_WORDS };

const cap = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s);
const article = (s: string) => (/^[aeiou]/i.test(s) ? "an" : "a");

/** Live vocabulary. Lower case, Capitalised and with an article ("a dealer" / "An item"). */
export const vocab = {
  get item() { return words.item; },
  get items() { return words.items; },
  get partner() { return words.partner; },
  get partners() { return words.partners; },
  get site() { return words.site; },
  get sites() { return words.sites; },
  get Item() { return cap(words.item); },
  get Items() { return cap(words.items); },
  get Partner() { return cap(words.partner); },
  get Partners() { return cap(words.partners); },
  get Site() { return cap(words.site); },
  get Sites() { return cap(words.sites); },
  get aItem() { return `${article(words.item)} ${words.item}`; },
  get AItem() { return cap(`${article(words.item)} ${words.item}`); },
  get aPartner() { return `${article(words.partner)} ${words.partner}`; },
  get APartner() { return cap(`${article(words.partner)} ${words.partner}`); },
  get aSite() { return `${article(words.site)} ${words.site}`; },
  get ASite() { return cap(`${article(words.site)} ${words.site}`); },
};

/** Replace the words (from the server configuration). Unknown keys and empty values are ignored. */
export function setWords(next: Partial<Record<string, string>> | null | undefined): void {
  for (const k of TERM_KEYS) {
    const v = next?.[k];
    if (typeof v === "string" && v.trim()) words[k] = v.trim();
  }
}

/** Back to the default words (tests). */
export function resetWords(): void {
  Object.assign(words, DEFAULT_WORDS);
}
