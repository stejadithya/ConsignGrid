/**
 * Search the way people say it: case, spaces and punctuation are ignored, and every word typed must appear.
 * "195 65", "19565", "195/65" and "195-65" all find 195/65R15; "ecodrive 195" finds an EcoDrive in a 195 width.
 */
const compact = (v: string) => v.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "");

/** The words of a query, each without punctuation ("195/65 R15" → ["195", "65", "r15"]). */
export function searchTokens(query: string): string[] {
  return query.split(/[\s/\\\-_.,;:+|]+/).map(compact).filter(Boolean);
}

/** True when every word of the query appears in the text (ignoring case, spaces and punctuation). With several texts
 *  (a table row's columns), each word must appear within one of them, never across a boundary between two. */
export function matchesSearch(text: string | readonly string[], query: string): boolean {
  const tokens = searchTokens(query);
  if (!tokens.length) return true;
  const hay = (typeof text === "string" ? [text] : text).map(compact);
  return tokens.every((t) => hay.some((h) => h.includes(t)));
}
