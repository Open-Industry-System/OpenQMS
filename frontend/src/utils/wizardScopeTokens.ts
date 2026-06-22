/**
 * DFMEA 向导 5T「工具/趋势」字段的 token 序列化工具。
 * 存盘为「、」(顿号) 分隔的 string；内存为 string[] 供 antd Select mode="tags" 使用。
 * 双向都做 trim、去空、去重（保持首次出现顺序），避免「手输 + chip toggle + AI chip」产生重复 tag。
 */

const SEPARATOR = "、";
const SPLIT_RE = /[、,;，；]/;

/** 「、,;，；」分隔的 string → 去空去重保序的 string[]。 */
export function parseScopeTokens(s: string | null | undefined): string[] {
  if (!s) return [];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of s.split(SPLIT_RE)) {
    const tok = raw.trim();
    if (!tok || seen.has(tok)) continue;
    seen.add(tok);
    out.push(tok);
  }
  return out;
}

/** string[] → 「、」分隔的 string（同样 trim、去空、去重保序）。 */
export function stringifyScopeTokens(arr: string[] | null | undefined): string {
  if (!arr || arr.length === 0) return "";
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of arr) {
    const tok = raw.trim();
    if (!tok || seen.has(tok)) continue;
    seen.add(tok);
    out.push(tok);
  }
  return out.join(SEPARATOR);
}
