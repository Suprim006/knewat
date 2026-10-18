import { describe, expect, it } from 'vitest';
import { errorMessage } from './errors';
import { costText, fmt, fmtInt, fmtMs, pFmt } from './format';

describe('number formatting for the Results page', () => {
  it('prints integers as-is and others with 2 decimals below 10, else 1', () => {
    expect(fmt(7)).toBe('7');
    expect(fmt(3.14159)).toBe('3.14');
    expect(fmt(12.34)).toBe('12.3');
  });

  it('switches ms to seconds at 1000', () => {
    expect(fmtMs(250)).toBe('250 ms');
    expect(fmtMs(1500)).toBe('1.50 s');
  });

  it('groups thousands and floors p-values at < 0.001', () => {
    expect(fmtInt(15930.4)).toBe('15,930');
    expect(pFmt(0.0004)).toBe('< 0.001');
    expect(pFmt(0.04321)).toBe('0.043');
  });

  it('describes the LLM cost of an arm', () => {
    const row = { arm: 'B0' } as Parameters<typeof costText>[0];
    expect(costText(row)).toBe('-');
    expect(costText({ ...row, costUsd: 0 })).toBe('$0 (no LLM)');
    expect(costText({ ...row, costUsd: 2.6683, costPerQuestionUsd: 0.062 })).toBe(
      '$2.67 ($0.062 / question)',
    );
  });
});

describe('errorMessage', () => {
  it('reads Error messages and stringifies anything else', () => {
    expect(errorMessage(new Error('boom'))).toBe('boom');
    expect(errorMessage('plain')).toBe('plain');
    expect(errorMessage(404)).toBe('404');
  });
});
