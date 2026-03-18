import { readFile, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';

export interface RateLimitEntry {
  limited_at: string;
  retry_after?: number;
  reason: 'rate_limit' | 'unavailable' | 'error';
}

export interface RateLimitState {
  [modelId: string]: RateLimitEntry;
}

function getRateLimitFile(): string {
  return process.env.RATE_LIMIT_FILE || 'rate-limit-state.json';
}
const RATE_LIMIT_COOLDOWN_MINUTES = 30;

let memoryState: RateLimitState | null = null;

export function resetRateLimitState(): void {
  memoryState = null;
}

export async function loadRateLimitState(): Promise<RateLimitState> {
  if (memoryState) return memoryState;

  const file = getRateLimitFile();
  if (!existsSync(file)) {
    memoryState = {};
    return memoryState;
  }

  try {
    const content = await readFile(file, 'utf-8');
    memoryState = JSON.parse(content) as RateLimitState;
    return memoryState;
  } catch {
    memoryState = {};
    return memoryState;
  }
}

export async function saveRateLimitState(state: RateLimitState): Promise<void> {
  memoryState = state;
  await writeFile(getRateLimitFile(), JSON.stringify(state, null, 2));
}

export function isModelRateLimited(modelId: string): boolean {
  const state: RateLimitState = memoryState || {};
  const record = state[modelId];
  if (!record) return false;

  const limitedAt = new Date(record.limited_at);
  const cooldownEnd = new Date(limitedAt.getTime() + RATE_LIMIT_COOLDOWN_MINUTES * 60 * 1000);
  return Date.now() < cooldownEnd.getTime();
}

export async function markModelRateLimited(
  modelId: string,
  reason: 'rate_limit' | 'unavailable' | 'error' = 'rate_limit',
  retryAfter?: number
): Promise<void> {
  const state = await loadRateLimitState();
  state[modelId] = {
    limited_at: new Date().toISOString(),
    retry_after: retryAfter,
    reason
  };
  await saveRateLimitState(state);
}

export async function cleanExpiredRateLimits(): Promise<void> {
  const state = await loadRateLimitState();
  const now = Date.now();
  const cooldownMs = RATE_LIMIT_COOLDOWN_MINUTES * 60 * 1000;

  const cleaned: RateLimitState = {};
  for (const [modelId, entry] of Object.entries(state)) {
    const limitedAt = new Date(entry.limited_at).getTime();
    if (now - limitedAt < cooldownMs) {
      cleaned[modelId] = entry;
    }
  }

  await saveRateLimitState(cleaned);
}