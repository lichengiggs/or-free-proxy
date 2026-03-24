import { afterEach, beforeEach, describe, expect, jest, test } from '@jest/globals';
import { existsSync, rmSync } from 'node:fs';

import {
  __MODEL_DICTIONARY_TEST_ONLY__,
  applyHardRules,
  loadModelDictionary,
  normalizeParamsToB,
  orderModelsByDictionary,
  triggerBackgroundDictionaryUpdate,
  type ModelDictionaryFile,
} from '../src/model-dictionary';
import type { Model } from '../src/providers/types';

const originalFetch = global.fetch;
const TEST_DICTIONARY_PATH = 'data/models.dev.test.json';

function mockResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' }
  });
}

describe('model dictionary module', () => {
  beforeEach(() => {
    process.env.MODEL_DICTIONARY_PATH = TEST_DICTIONARY_PATH;
    process.env.MODELS_DEV_URL = 'https://models.dev/api.json';
    __MODEL_DICTIONARY_TEST_ONLY__.clearCache();
    if (existsSync(TEST_DICTIONARY_PATH)) rmSync(TEST_DICTIONARY_PATH, { force: true });
  });

  afterEach(() => {
    global.fetch = originalFetch;
    __MODEL_DICTIONARY_TEST_ONLY__.clearCache();
    if (existsSync(TEST_DICTIONARY_PATH)) rmSync(TEST_DICTIONARY_PATH, { force: true });
    delete process.env.MODEL_DICTIONARY_PATH;
    delete process.env.MODELS_DEV_URL;
  });

  test('keeps unknown parameter models while filtering explicit small models', () => {
    expect(normalizeParamsToB(undefined, 'gemini-2.5-flash-preview-09-2025')).toBeNull();
    expect(normalizeParamsToB(undefined, 'google/gemma-3n-e2b-it')).toBe(0);
  });

  test('marks missing params as field_missing instead of filtering', () => {
    expect(
      applyHardRules({
        params_b: null,
        input_context_limit: 128000,
        output_context_limit: 16000,
        release_year: 2025,
        tool_support_flag: true
      })
    ).toEqual({ keep: true, field_missing: true });
  });

  test('writes filtered dictionary file and preserves unknown params entries', async () => {
    global.fetch = jest.fn<typeof fetch>().mockResolvedValue(
      mockResponse({
        data: [
          {
            provider_id: 'google',
            model_id: 'gemini-2.5-flash-preview-09-2025',
            name: 'Gemini 2.5 Flash Preview 09-2025',
            release_date: '2025-09-01',
            input_context_limit: '128k',
            output_context_limit: '16k',
            supports_tools: true,
            tags: ['tool-call']
          },
          {
            provider_id: 'google',
            model_id: 'gemma-3n-e2b-it',
            name: 'Gemma 3n e2b IT',
            release_date: '2025-06-01',
            input_context_limit: '128k',
            output_context_limit: '16k',
            supports_tools: true,
            tags: ['tool-call']
          }
        ]
      })
    );

    await triggerBackgroundDictionaryUpdate();
    const dictionary = await loadModelDictionary(true);

    expect(dictionary).not.toBeNull();
    const models = dictionary?.models ?? [];
    expect(models.map(model => model.id)).toEqual(['google/gemini-2.5-flash-preview-09-2025']);
    expect(models[0]?.field_missing).toBe(true);
    expect(models[0]?.rank).toBe(1);
  });

  test('keeps tier A models before tier B and preserves unknown params neutrality', () => {
    const dictionary: ModelDictionaryFile = {
      updated_at: '2026-03-24T00:00:00.000Z',
      models: [
        {
          id: 'google/gemini-2.5-flash',
          model_id: 'gemini-2.5-flash',
          name: 'Gemini 2.5 Flash',
          provider_id: 'google',
          tier: 'A',
          params_b: null,
          input_context_limit: 256000,
          output_context_limit: 32000,
          release_year: 2025,
          release_at: '2025-09',
          tags: [],
          source: 'models.dev',
          tool_support_flag: true,
          field_missing: true,
          rank: 1,
          updated_at: '2026-03-24T00:00:00.000Z',
          raw: {}
        },
        {
          id: 'vendor/lab-model',
          model_id: 'lab-model',
          name: 'Lab Model',
          provider_id: 'vendor',
          tier: 'B',
          params_b: 70,
          input_context_limit: 256000,
          output_context_limit: 32000,
          release_year: 2025,
          release_at: '2025-10',
          tags: [],
          source: 'models.dev',
          tool_support_flag: true,
          rank: 2,
          updated_at: '2026-03-24T00:00:00.000Z',
          raw: {}
        }
      ]
    };

    const models: Model[] = [
      { id: 'vendor/lab-model', name: 'Lab Model', provider: 'vendor', pricing: { prompt: '0', completion: '0' } },
      { id: 'google/gemini-2.5-flash', name: 'Gemini 2.5 Flash', provider: 'google', pricing: { prompt: '0', completion: '0' } }
    ];

    const ordered = orderModelsByDictionary(models, dictionary);
    expect(ordered.map(model => model.id)).toEqual([
      'google/gemini-2.5-flash',
      'vendor/lab-model'
    ]);
  });

  test('returns null when dictionary file does not exist', async () => {
    const dictionary = await loadModelDictionary();
    expect(dictionary).toBeNull();
  });
});
