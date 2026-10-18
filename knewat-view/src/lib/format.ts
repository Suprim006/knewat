import type { L2Row } from './results';

/** Number formatting for the Results page. Integers print as-is; others get 2 decimals below 10, else 1. */
export const fmt = (n: number): string => (Number.isInteger(n) ? String(n) : n.toFixed(n < 10 ? 2 : 1));
const fmtUsd = (n: number): string => `$${n.toFixed(n < 1 ? 3 : 2)}`;
export const fmtMs = (n: number): string => (n >= 1000 ? `${(n / 1000).toFixed(2)} s` : `${fmt(n)} ms`);
export const fmtInt = (n: number): string => Math.round(n).toLocaleString('en-US');

/** p-value: floors at "< 0.001". */
export function pFmt(p: number): string {
  return p < 0.001 ? '< 0.001' : p.toFixed(3);
}

/** LLM cost of an L2 arm: "-" when unknown, "$0 (no LLM)" for the Knewat answerer. */
export function costText(x: L2Row): string {
  if (x.costUsd === undefined) return '-';
  return x.costUsd === 0
    ? '$0 (no LLM)'
    : `${fmtUsd(x.costUsd)} (${fmtUsd(x.costPerQuestionUsd ?? 0)} / question)`;
}
