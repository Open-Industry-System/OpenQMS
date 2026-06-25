import type { TFunction } from "i18next";

/**
 * 把后端已知的英文错误 detail 映射成本地化文案。
 * FMEA 后端有少数错误是英文（编号重复 / 非法状态转换 / 未找到），
 * 其余多数本身就是中文；未命中的原样返回，让中文消息直接透传。
 */
export function formatFMEAError(detail: string | undefined, t: TFunction): string {
  if (!detail) return "";

  // FMEA document number 'XXX' already exists.
  const dup = detail.match(/document number '([^']+)' already exists/i);
  if (dup) return t("messages.documentNoExists", { no: dup[1] });

  // Cannot transition from X to Y. Allowed: [...]
  const tr = detail.match(/^Cannot transition from (\w+) to (\w+)\. Allowed: (.+)$/);
  if (tr) return t("messages.cannotTransition", { from: tr[1], to: tr[2], allowed: tr[3] });

  if (/^FMEA not found$/i.test(detail)) return t("messages.notFound");

  return detail;
}
