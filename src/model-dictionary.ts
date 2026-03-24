import { copyFile, mkdir, readFile, rename, unlink, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { dirname } from 'node:path';
import type { Model } from './providers/types';

export type Tier = 'A' | 'B';

type JsonPrimitive = boolean | number | string | null;
type JsonValue = JsonPrimitive | JsonObject | JsonValue[];
type JsonObject = { [key: string]: JsonValue };

type MaybeNumber = number | null;
type MaybeString = string | null;

type RawModelsDevEntry = JsonObject & {
  capabilities?: JsonValue;
  description?: JsonValue;
  family?: JsonValue;
  id?: JsonValue;
  input_context_limit?: JsonValue;
  license?: JsonValue;
  model?: JsonValue;
  model_family?: JsonValue;
  model_id?: JsonValue;
  name?: JsonValue;
  output_context_limit?: JsonValue;
  parameters?: JsonValue;
  provider?: JsonValue;
  provider_id?: JsonValue;
  published_at?: JsonValue;
  release_at?: JsonValue;
  release_date?: JsonValue;
  size?: JsonValue;
  source?: JsonValue;
  supports_function_calling?: JsonValue;
  supports_tools?: JsonValue;
  tags?: JsonValue;
  tool_call?: JsonValue;
  tool_use?: JsonValue;
  url?: JsonValue;
  weights?: JsonValue;
};

export type ModelDictionaryEntry = {
  id: string;
  model_id: string;
  name: string;
  provider_id: string;
  family?: MaybeString;
  tier: Tier;
  params_b: MaybeNumber;
  input_context_limit: MaybeNumber;
  output_context_limit: MaybeNumber;
  release_year: MaybeNumber;
  release_at?: MaybeString;
  license?: MaybeString;
  url?: MaybeString;
  tags: string[];
  source: 'models.dev';
  tool_support_flag: boolean;
  field_missing?: boolean;
  rank: number;
  updated_at: string;
  raw: JsonObject;
};

export type ModelDictionaryFile = {
  updated_at: string;
  models: ModelDictionaryEntry[];
};

export type UpdateModelsDictionaryResult = {
  success: boolean;
  updated: boolean;
  path: string;
  count?: number;
  error?: string;
};

const DEFAULT_MODELS_DEV_URL = 'https://models.dev/api.json';
const DEFAULT_DICTIONARY_PATH = 'data/models.dev.json';
const RETRY_DELAYS = [1000, 2000, 4000];
const MIN_INPUT_CONTEXT = 100000;
const MIN_OUTPUT_CONTEXT = 10000;
const MIN_RELEASE_YEAR = 2025;
const MIN_PARAMS_B = 10;

const TIER_A_FAMILIES = ['gpt', 'claude', 'deepseek', 'gemini', 'glm', 'kimi', 'mimo', 'minimax', 'step'];

const FAMILY_ALIAS: Record<string, string> = {
  'chatgpt': 'gpt',
  'gpt-5': 'gpt',
  'moonshot': 'kimi',
  'kimi-k2': 'kimi',
  'minimaxai': 'minimax'
};

const EXPLICIT_SMALL_MODEL_PATTERNS = [
  'gemma-3n-e2b',
  'gemma-3n-e4b',
  'mistral-small',
  'phi-3-mini',
  'phi-3.5-mini'
];

const TIER_A_SET = new Set(TIER_A_FAMILIES);

let cachedDictionaryPath: string | null = null;
let cachedDictionary: ModelDictionaryFile | null = null;
let backgroundUpdate: Promise<void> | null = null;

function getDictionaryPath(): string {
  return process.env.MODEL_DICTIONARY_PATH || DEFAULT_DICTIONARY_PATH;
}

function getModelsDevUrl(): string {
  return process.env.MODELS_DEV_URL || DEFAULT_MODELS_DEV_URL;
}

function isJsonObject(value: JsonValue | undefined): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isRawModelsDevEntry(value: JsonValue | undefined): value is RawModelsDevEntry {
  return isJsonObject(value);
}

function asString(value: JsonValue | undefined): string | null {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : null;
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    return String(value);
  }
  return null;
}

function asBoolean(value: JsonValue | undefined): boolean | null {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    if (normalized === 'true' || normalized === 'yes') return true;
    if (normalized === 'false' || normalized === 'no') return false;
  }
  return null;
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function roundTo(value: number, digits: number): number {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function normalizeFamily(value: string | null | undefined): string {
  if (!value) return '';
  const normalized = value.trim().toLowerCase();
  return FAMILY_ALIAS[normalized] || normalized;
}

function splitTags(value: JsonValue | undefined): string[] {
  if (Array.isArray(value)) {
    return value
      .map(item => (typeof item === 'string' ? item.trim().toLowerCase() : ''))
      .filter(item => item.length > 0);
  }

  if (typeof value === 'string') {
    return value
      .split(/[|,/\s]+/)
      .map(item => item.trim().toLowerCase())
      .filter(item => item.length > 0);
  }

  return [];
}

function getNestedNumber(object: JsonObject, key: string): number | null {
  return normalizeNumber(object[key]);
}

function normalizeNumber(value: JsonValue | undefined): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;

  const text = asString(value);
  if (!text) return null;

  const normalized = text.replace(/,/g, '').trim().toLowerCase();
  const multiplierMatch = normalized.match(/^(\d+(?:\.\d+)?)(k|m)?$/);
  if (multiplierMatch) {
    const base = parseFloat(multiplierMatch[1]);
    const suffix = multiplierMatch[2];
    if (suffix === 'k') return Math.round(base * 1024);
    if (suffix === 'm') return Math.round(base * 1024 * 1024);
    return base;
  }

  return null;
}

function parseDateParts(value: string | null): { year: number; month: number } | null {
  if (!value) return null;
  const trimmed = value.trim();

  let match = trimmed.match(/^(\d{4})-(\d{2})/);
  if (match) {
    const year = Number(match[1]);
    const month = Number(match[2]);
    if (Number.isFinite(year) && Number.isFinite(month) && month >= 1 && month <= 12) {
      return { year, month };
    }
  }

  match = trimmed.match(/^(\d{4})$/);
  if (match) {
    const year = Number(match[1]);
    if (Number.isFinite(year)) {
      return { year, month: 1 };
    }
  }

  return null;
}

function getReleaseSource(entry: RawModelsDevEntry): string | null {
  return asString(entry.release_date)
    || asString(entry.release_at)
    || asString(entry.published_at);
}

function getLimitObject(entry: RawModelsDevEntry): JsonObject | null {
  const limit = entry.limit;
  return isJsonObject(limit) ? limit : null;
}

export function normalizeReleaseAt(value: string | null | undefined): string | null {
  const parts = parseDateParts(value || null);
  if (!parts) return null;
  return `${parts.year}-${String(parts.month).padStart(2, '0')}`;
}

export function normalizeReleaseYear(value: string | null | undefined): number | null {
  const parts = parseDateParts(value || null);
  return parts?.year ?? null;
}

function toReleaseMonthIndex(releaseAt: string | null | undefined, releaseYear: number | null | undefined): number {
  const parts = parseDateParts(releaseAt || null);
  if (parts) return parts.year * 12 + parts.month;
  return releaseYear != null ? releaseYear * 12 + 1 : 0;
}

function parseParametersFromText(text: string): number | null {
  const normalized = text.trim().toLowerCase().replace(/,/g, '');
  const moeMatch = normalized.match(/(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*b\b/);
  if (moeMatch) {
    return roundTo(parseFloat(moeMatch[1]) * parseFloat(moeMatch[2]), 3);
  }

  const bMatch = normalized.match(/(\d+(?:\.\d+)?)\s*(?:b|bn|billion)\b/);
  if (bMatch) {
    return parseFloat(bMatch[1]);
  }

  const eMatch = normalized.match(/(?:^|[-_ /])e(\d+(?:\.\d+)?)b(?:\b|$)/);
  if (eMatch) {
    return parseFloat(eMatch[1]);
  }

  const digitsMatch = normalized.match(/^(\d+(?:\.\d+)?)$/);
  if (digitsMatch) {
    const value = parseFloat(digitsMatch[1]);
    if (value > 1000) return roundTo(value / 1_000_000_000, 3);
    return value;
  }

  return null;
}

function inferParamsFromName(modelId?: string, name?: string): number | null {
  const haystack = `${modelId || ''} ${name || ''}`.toLowerCase();
  for (const pattern of EXPLICIT_SMALL_MODEL_PATTERNS) {
    if (haystack.includes(pattern)) {
      return 0;
    }
  }

  return parseParametersFromText(haystack);
}

export function normalizeParamsToB(
  parameters: string | number | null | undefined,
  modelId?: string,
  name?: string,
): number | null {
  if (typeof parameters === 'number' && Number.isFinite(parameters)) {
    if (parameters > 1000) return roundTo(parameters / 1_000_000_000, 3);
    return parameters;
  }

  if (typeof parameters === 'string' && parameters.trim().length > 0) {
    const parsed = parseParametersFromText(parameters);
    if (parsed != null) return parsed;
  }

  const inferred = inferParamsFromName(modelId, name);
  if (inferred === 0) return 0;
  return inferred;
}

function detectFamily(entry: Pick<ModelDictionaryEntry, 'family' | 'id' | 'name'>): string {
  const baseFamily = normalizeFamily(entry.family || null);
  if (baseFamily) return baseFamily;

  const haystack = `${entry.id} ${entry.name}`.toLowerCase();
  if (haystack.includes('minimax')) return 'minimax';
  if (haystack.includes('claude')) return 'claude';
  if (haystack.includes('gemini')) return 'gemini';
  if (haystack.includes('deepseek')) return 'deepseek';
  if (haystack.includes('moonshot') || haystack.includes('kimi')) return 'kimi';
  if (haystack.includes('glm')) return 'glm';
  if (haystack.includes('mimo')) return 'mimo';
  if (haystack.includes('step')) return 'step';
  if (haystack.includes('gpt') || haystack.includes('chatgpt')) return 'gpt';
  return '';
}

export function buildTier(entry: Pick<ModelDictionaryEntry, 'family' | 'id' | 'name'>): Tier {
  return TIER_A_SET.has(detectFamily(entry)) ? 'A' : 'B';
}

function detectToolSupport(entry: RawModelsDevEntry, tags: string[]): boolean {
  const directFlags = [
    asBoolean(entry.supports_tools),
    asBoolean(entry.supports_function_calling),
    asBoolean(entry.tool_call),
    asBoolean(entry.tool_use)
  ];

  if (directFlags.includes(true)) return true;

  const description = asString(entry.description)?.toLowerCase() || '';
  const haystack = [description, ...tags].join(' ');
  return haystack.includes('tool') || haystack.includes('function-call') || haystack.includes('function_call');
}

function buildCompositeId(providerId: string | null, modelId: string | null, fallbackId: string | null): {
  id: string;
  providerId: string;
  modelId: string;
} | null {
  if (providerId && modelId) {
    return {
      id: `${providerId}/${modelId}`,
      providerId,
      modelId
    };
  }

  if (fallbackId) {
    const parts = fallbackId.split('/');
    if (parts.length >= 2) {
      return {
        id: fallbackId,
        providerId: parts[0],
        modelId: parts.slice(1).join('/')
      };
    }

    return {
      id: fallbackId,
      providerId: 'unknown',
      modelId: fallbackId
    };
  }

  return null;
}

function normalizeEntry(rawEntry: RawModelsDevEntry, updatedAt: string): ModelDictionaryEntry | null {
  const fallbackId = asString(rawEntry.id);
  const providerId = asString(rawEntry.provider_id) || asString(rawEntry.provider);
  const modelId = asString(rawEntry.model_id) || asString(rawEntry.model);
  const composite = buildCompositeId(providerId, modelId, fallbackId);
  if (!composite) return null;

  const name = asString(rawEntry.name) || composite.modelId;
  const tags = [...splitTags(rawEntry.tags), ...splitTags(rawEntry.capabilities)];
  const releaseSource = getReleaseSource(rawEntry);
  const family = asString(rawEntry.family) || asString(rawEntry.model_family);
  const limit = getLimitObject(rawEntry);
  const inputContextLimit = normalizeNumber(rawEntry.input_context_limit) ?? (limit ? getNestedNumber(limit, 'context') : null);
  const outputContextLimit = normalizeNumber(rawEntry.output_context_limit) ?? (limit ? getNestedNumber(limit, 'output') : null);

  const entry: ModelDictionaryEntry = {
    id: composite.id,
    model_id: composite.modelId,
    name,
    provider_id: composite.providerId,
    family,
    tier: 'B',
    params_b: normalizeParamsToB(
      asString(rawEntry.parameters) || asString(rawEntry.weights) || asString(rawEntry.size),
      composite.modelId,
      name,
    ),
    input_context_limit: inputContextLimit,
    output_context_limit: outputContextLimit,
    release_year: normalizeReleaseYear(releaseSource),
    release_at: normalizeReleaseAt(releaseSource),
    license: asString(rawEntry.license),
    url: asString(rawEntry.url),
    tags,
    source: 'models.dev',
    tool_support_flag: detectToolSupport(rawEntry, tags),
    rank: 0,
    updated_at: updatedAt,
    raw: rawEntry
  };

  entry.tier = buildTier(entry);
  return entry;
}

export function applyHardRules(
  entry: Pick<
    ModelDictionaryEntry,
    'input_context_limit' | 'output_context_limit' | 'params_b' | 'release_year' | 'tool_support_flag'
  >,
): { keep: boolean; field_missing?: boolean } {
  if (entry.params_b != null && entry.params_b < MIN_PARAMS_B) return { keep: false };
  if (entry.release_year == null || entry.release_year < MIN_RELEASE_YEAR) return { keep: false };
  if (!entry.tool_support_flag) return { keep: false };

  const hasContext = entry.input_context_limit != null && entry.output_context_limit != null;
  const hasMissingField = entry.params_b == null || !hasContext;

  if (!hasContext) {
    return {
      keep: true,
      field_missing: hasMissingField ? true : undefined
    };
  }

  const inputContext = entry.input_context_limit;
  const outputContext = entry.output_context_limit;

  if (inputContext == null || outputContext == null) {
    return {
      keep: true,
      field_missing: true
    };
  }

  if (inputContext < MIN_INPUT_CONTEXT) return { keep: false };
  if (outputContext < MIN_OUTPUT_CONTEXT) return { keep: false };

  return {
    keep: true,
    field_missing: hasMissingField ? true : undefined
  };
}

function computeContextStrength(entry: Pick<ModelDictionaryEntry, 'input_context_limit' | 'output_context_limit'>): number {
  if (entry.input_context_limit == null || entry.output_context_limit == null) return 0;
  return entry.input_context_limit + entry.output_context_limit;
}

function compareDictionaryEntries(a: ModelDictionaryEntry, b: ModelDictionaryEntry): number {
  if (a.tier !== b.tier) return a.tier === 'A' ? -1 : 1;

  const contextDiff = computeContextStrength(b) - computeContextStrength(a);
  if (contextDiff !== 0) return contextDiff;

  const monthDiff = toReleaseMonthIndex(b.release_at, b.release_year) - toReleaseMonthIndex(a.release_at, a.release_year);
  if (monthDiff !== 0) return monthDiff;

  const paramsDiff = (b.params_b ?? -1) - (a.params_b ?? -1);
  if (paramsDiff !== 0) return paramsDiff;

  return a.id.localeCompare(b.id);
}

export function sortEntries(entries: ModelDictionaryEntry[]): ModelDictionaryEntry[] {
  return [...entries]
    .sort(compareDictionaryEntries)
    .map((entry, index) => ({
      ...entry,
      rank: index + 1
    }));
}

function extractRawEntries(payload: JsonValue): RawModelsDevEntry[] {
  if (Array.isArray(payload)) {
    return payload.filter(isJsonObject) as RawModelsDevEntry[];
  }

  if (!isJsonObject(payload)) return [];

  const candidates = [payload.data, payload.models, payload.items];
  for (const candidate of candidates) {
    if (Array.isArray(candidate)) {
      return candidate.filter(isJsonObject) as RawModelsDevEntry[];
    }
  }

  const flattened: RawModelsDevEntry[] = [];
  for (const [providerId, providerValue] of Object.entries(payload)) {
    if (!isJsonObject(providerValue)) continue;
    const providerModels = providerValue.models;
    if (!isJsonObject(providerModels)) continue;

    for (const [modelId, modelValue] of Object.entries(providerModels)) {
      if (!isRawModelsDevEntry(modelValue)) continue;
      flattened.push({
        ...modelValue,
        provider_id: asString(modelValue.provider_id) || providerId,
        model_id: asString(modelValue.model_id) || modelId,
        id: asString(modelValue.id) || `${providerId}/${modelId}`
      });
    }
  }

  if (flattened.length > 0) return flattened;

  return [];
}

async function sleep(ms: number): Promise<void> {
  await new Promise(resolve => setTimeout(resolve, ms));
}

async function fetchModelsDevPayload(): Promise<JsonValue> {
  const url = getModelsDevUrl();

  for (let index = 0; index < RETRY_DELAYS.length; index += 1) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(10000) });
      if (!response.ok) {
        throw new Error(`models.dev request failed with HTTP ${response.status}`);
      }

      return await response.json() as JsonValue;
    } catch (error) {
      if (index === RETRY_DELAYS.length - 1) {
        throw error instanceof Error ? error : new Error('Failed to fetch models.dev');
      }
      await sleep(RETRY_DELAYS[index]);
    }
  }

  throw new Error('Failed to fetch models.dev');
}

function withFieldMissing(entry: ModelDictionaryEntry, fieldMissing: boolean | undefined): ModelDictionaryEntry {
  return {
    ...entry,
    field_missing: fieldMissing || undefined
  };
}

function buildDictionary(entries: RawModelsDevEntry[]): ModelDictionaryFile {
  const updatedAt = new Date().toISOString();
  const normalized = entries
    .map(entry => normalizeEntry(entry, updatedAt))
    .filter((entry): entry is ModelDictionaryEntry => entry !== null)
    .map(entry => {
      const hardRules = applyHardRules(entry);
      return {
        entry,
        hardRules
      };
    })
    .filter(item => item.hardRules.keep)
    .map(item => withFieldMissing(item.entry, item.hardRules.field_missing));

  return {
    updated_at: updatedAt,
    models: sortEntries(normalized).map(entry => ({
      ...entry,
      updated_at: updatedAt
    }))
  };
}

async function writeDictionaryAtomically(dictionary: ModelDictionaryFile): Promise<void> {
  const targetPath = getDictionaryPath();
  const directory = dirname(targetPath);
  const tmpPath = `${targetPath}.tmp`;

  await mkdir(directory, { recursive: true });

  if (existsSync(targetPath)) {
    await copyFile(targetPath, `${targetPath}.bak.${Date.now()}`);
  }

  try {
    await writeFile(tmpPath, JSON.stringify(dictionary, null, 2), 'utf8');
    await rename(tmpPath, targetPath);
  } catch (error) {
    if (existsSync(tmpPath)) {
      await unlink(tmpPath);
    }
    throw error;
  }
}

export async function updateModelsDictionary(): Promise<UpdateModelsDictionaryResult> {
  const path = getDictionaryPath();

  try {
    const payload = await fetchModelsDevPayload();
    const rawEntries = extractRawEntries(payload);
    const dictionary = buildDictionary(rawEntries);

    if (dictionary.models.length === 0) {
      return {
        success: false,
        updated: false,
        path,
        error: 'empty_result'
      };
    }

    await writeDictionaryAtomically(dictionary);
    cachedDictionaryPath = path;
    cachedDictionary = dictionary;

    return {
      success: true,
      updated: true,
      path,
      count: dictionary.models.length
    };
  } catch (error) {
    return {
      success: false,
      updated: false,
      path,
      error: error instanceof Error ? error.message : 'unknown_error'
    };
  }
}

export async function loadModelDictionary(forceRefresh = false): Promise<ModelDictionaryFile | null> {
  const path = getDictionaryPath();
  if (!forceRefresh && cachedDictionary && cachedDictionaryPath === path) {
    return cachedDictionary;
  }

  if (!existsSync(path)) return null;

  try {
    const content = await readFile(path, 'utf8');
    const parsed = JSON.parse(content) as ModelDictionaryFile;
    cachedDictionaryPath = path;
    cachedDictionary = parsed;
    return parsed;
  } catch {
    return null;
  }
}

export async function triggerBackgroundDictionaryUpdate(): Promise<void> {
  if (backgroundUpdate) {
    await backgroundUpdate;
    return;
  }

  backgroundUpdate = (async () => {
    try {
      const result = await updateModelsDictionary();
      if (!result.success && process.env.NODE_ENV !== 'test') {
        console.error(`[ModelDictionary] update failed: ${result.error || 'unknown_error'}`);
      }
    } finally {
      backgroundUpdate = null;
    }
  })();

  await backgroundUpdate;
}

function toDictionaryComparable(model: Model, dictionaryEntry?: ModelDictionaryEntry): ModelDictionaryEntry {
  if (dictionaryEntry) return dictionaryEntry;

  const params = normalizeParamsToB(null, model.id, model.name);
  const pseudo: ModelDictionaryEntry = {
    id: model.id,
    model_id: model.id.split('/').slice(1).join('/') || model.id,
    name: model.name,
    provider_id: model.provider,
    family: null,
    tier: buildTier({ id: model.id, name: model.name, family: null }),
    params_b: params,
    input_context_limit: model.context_length ?? null,
    output_context_limit: 0,
    release_year: null,
    release_at: null,
    license: null,
    url: null,
    tags: [],
    source: 'models.dev',
    tool_support_flag: true,
    field_missing: params == null ? true : undefined,
    rank: Number.MAX_SAFE_INTEGER,
    updated_at: '',
    raw: {}
  };

  return pseudo;
}

export function orderModelsByDictionary(models: Model[], dictionary: ModelDictionaryFile | null): Model[] {
  if (models.length <= 1) return models.slice();
  const dictionaryMap = new Map<string, ModelDictionaryEntry>();
  for (const entry of dictionary?.models || []) {
    dictionaryMap.set(entry.id, entry);
  }

  return [...models].sort((left, right) => {
    const leftEntry = toDictionaryComparable(left, dictionaryMap.get(left.id));
    const rightEntry = toDictionaryComparable(right, dictionaryMap.get(right.id));
    return compareDictionaryEntries(leftEntry, rightEntry);
  });
}

export const __MODEL_DICTIONARY_TEST_ONLY__ = {
  clearCache(): void {
    cachedDictionary = null;
    cachedDictionaryPath = null;
    backgroundUpdate = null;
  }
};
