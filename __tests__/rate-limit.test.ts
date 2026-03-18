import { describe, test, expect, beforeEach, afterEach } from '@jest/globals';
import { 
  loadRateLimitState, 
  saveRateLimitState, 
  isModelRateLimited, 
  markModelRateLimited,
  cleanExpiredRateLimits,
  resetRateLimitState
} from '../src/rate-limit';
import { existsSync, unlinkSync, writeFileSync } from 'node:fs';

const RATE_LIMIT_FILE = 'rate-limit-state.test.json';

describe('rate-limit module', () => {
  beforeEach(async () => {
    process.env.RATE_LIMIT_FILE = RATE_LIMIT_FILE;
    resetRateLimitState();
    if (existsSync(RATE_LIMIT_FILE)) {
      unlinkSync(RATE_LIMIT_FILE);
    }
  });

  afterEach(() => {
    if (existsSync(RATE_LIMIT_FILE)) {
      unlinkSync(RATE_LIMIT_FILE);
    }
    delete process.env.RATE_LIMIT_FILE;
  });

  describe('loadRateLimitState', () => {
    test('should return empty object when file does not exist', async () => {
      const state = await loadRateLimitState();
      expect(state).toEqual({});
    });

    test('should load state from file when it exists', async () => {
      const testState = {
        'model-1': {
          limited_at: new Date().toISOString(),
          reason: 'rate_limit' as const
        }
      };
      await saveRateLimitState(testState);
      resetRateLimitState();
      
      const loaded = await loadRateLimitState();
      expect(loaded['model-1']).toBeDefined();
      expect(loaded['model-1'].reason).toBe('rate_limit');
    });
  });

  describe('saveRateLimitState', () => {
    test('should save state to file', async () => {
      const state = {
        'test-model': {
          limited_at: new Date().toISOString(),
          reason: 'rate_limit' as const,
          retry_after: 3600
        }
      };
      
      await saveRateLimitState(state);
      expect(existsSync(RATE_LIMIT_FILE)).toBe(true);
      
      resetRateLimitState();
      const loaded = await loadRateLimitState();
      expect(loaded['test-model']).toBeDefined();
    });
  });

  describe('isModelRateLimited', () => {
    test('should return false when model is not in state', () => {
      resetRateLimitState();
      const result = isModelRateLimited('non-existent-model');
      expect(result).toBe(false);
    });

    test('should return true when model is within cooldown period', async () => {
      const state = {
        'limited-model': {
          limited_at: new Date().toISOString(),
          reason: 'rate_limit' as const
        }
      };
      await saveRateLimitState(state);
      
      const result = isModelRateLimited('limited-model');
      expect(result).toBe(true);
    });

    test('should return false when cooldown has expired', async () => {
      const thirtyOneMinutesAgo = new Date(Date.now() - 31 * 60 * 1000).toISOString();
      const state = {
        'expired-model': {
          limited_at: thirtyOneMinutesAgo,
          reason: 'rate_limit' as const
        }
      };
      await saveRateLimitState(state);
      
      const result = isModelRateLimited('expired-model');
      expect(result).toBe(false);
    });
  });

  describe('markModelRateLimited', () => {
    test('should mark model as rate limited', async () => {
      await markModelRateLimited('test-model', 'rate_limit', 3600);
      
      const state = await loadRateLimitState();
      expect(state['test-model']).toBeDefined();
      expect(state['test-model'].reason).toBe('rate_limit');
      expect(state['test-model'].retry_after).toBe(3600);
    });

    test('should mark model as unavailable', async () => {
      await markModelRateLimited('unavailable-model', 'unavailable');
      
      const state = await loadRateLimitState();
      expect(state['unavailable-model']).toBeDefined();
      expect(state['unavailable-model'].reason).toBe('unavailable');
    });

    test('should update existing record', async () => {
      await markModelRateLimited('model-a', 'rate_limit');
      const firstState = await loadRateLimitState();
      const firstTime = firstState['model-a'].limited_at;
      
      await new Promise(resolve => setTimeout(resolve, 10));
      
      await markModelRateLimited('model-a', 'unavailable');
      const secondState = await loadRateLimitState();
      
      expect(secondState['model-a'].reason).toBe('unavailable');
      expect(secondState['model-a'].limited_at).not.toBe(firstTime);
    });
  });

  describe('cleanExpiredRateLimits', () => {
    test('should remove expired rate limit records', async () => {
      const thirtyOneMinutesAgo = new Date(Date.now() - 31 * 60 * 1000).toISOString();
      const justNow = new Date().toISOString();
      
      const state = {
        'expired-1': {
          limited_at: thirtyOneMinutesAgo,
          reason: 'rate_limit' as const
        },
        'expired-2': {
          limited_at: thirtyOneMinutesAgo,
          reason: 'rate_limit' as const
        },
        'active': {
          limited_at: justNow,
          reason: 'rate_limit' as const
        }
      };
      await saveRateLimitState(state);
      
      await cleanExpiredRateLimits();
      
      const cleaned = await loadRateLimitState();
      expect(cleaned['expired-1']).toBeUndefined();
      expect(cleaned['expired-2']).toBeUndefined();
      expect(cleaned['active']).toBeDefined();
    });

    test('should handle empty state', async () => {
      await expect(cleanExpiredRateLimits()).resolves.not.toThrow();
    });
  });
});