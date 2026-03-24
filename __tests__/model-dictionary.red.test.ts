import { describe, expect, test } from '@jest/globals';

import {
  applyHardRules,
  buildTier,
  normalizeParamsToB,
  sortEntries,
  type ModelDictionaryEntry,
} from '../src/model-dictionary';

describe('model dictionary red phase', () => {
  test('normalizes explicit parameter strings into B units', () => {
    expect(normalizeParamsToB('70B', 'openai/gpt-oss-120b')).toBe(70);
    expect(normalizeParamsToB('67100000000', 'some/model')).toBe(67.1);
  });

  test('keeps unknown-parameter models unresolved instead of guessing a score', () => {
    expect(normalizeParamsToB(undefined, 'gemini-2.5-flash-preview-09-2025')).toBeNull();
    expect(normalizeParamsToB(undefined, 'minimax-m2.5')).toBeNull();
  });

  test('filters only when params are clearly below 10B', () => {
    expect(
      applyHardRules({
        params_b: 7,
        input_context_limit: 128000,
        output_context_limit: 16000,
        release_year: 2025,
        tool_support_flag: true,
      }),
    ).toEqual({ keep: false });
  });

  test('keeps valid unknown-parameter models and marks them as field_missing', () => {
    expect(
      applyHardRules({
        params_b: null,
        input_context_limit: 128000,
        output_context_limit: 16000,
        release_year: 2025,
        tool_support_flag: true,
      }),
    ).toEqual({ keep: true, field_missing: true });
  });

  test('classifies mainstream families into tier A from id or name', () => {
    expect(buildTier({ id: 'google/gemini-2.5-pro', name: 'Gemini 2.5 Pro' })).toBe('A');
    expect(buildTier({ id: 'minimax/minimax-m2.5', name: 'MiniMax M2.5' })).toBe('A');
    expect(buildTier({ id: 'unknown/lab-model', name: 'Lab Model' })).toBe('B');
  });

  test('sorts by tier, then context, then newer release month, then params', () => {
    const entries: ModelDictionaryEntry[] = [
      {
        id: 'vendor/alpha',
        name: 'Alpha',
        tier: 'B',
        params_b: 70,
        input_context_limit: 128000,
        output_context_limit: 16000,
        release_year: 2025,
        release_at: '2025-05',
        tool_support_flag: true,
      },
      {
        id: 'google/gemini-2.5-pro',
        name: 'Gemini 2.5 Pro',
        tier: 'A',
        params_b: 32,
        input_context_limit: 256000,
        output_context_limit: 32000,
        release_year: 2025,
        release_at: '2025-06',
        tool_support_flag: true,
      },
      {
        id: 'google/gemini-2.5-flash',
        name: 'Gemini 2.5 Flash',
        tier: 'A',
        params_b: null,
        input_context_limit: 256000,
        output_context_limit: 32000,
        release_year: 2025,
        release_at: '2025-09',
        tool_support_flag: true,
        field_missing: true,
      },
    ];

    expect(sortEntries(entries).map((entry) => entry.id)).toEqual([
      'google/gemini-2.5-flash',
      'google/gemini-2.5-pro',
      'vendor/alpha',
    ]);
  });
});
