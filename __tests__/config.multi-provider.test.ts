import { jest } from '@jest/globals';
import { unlinkSync, writeFileSync } from 'fs';
import { getProviderKey, saveProviderKey, getAllProviderKeysStatus } from '../src/config';

describe('Multi-Provider Key Management', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    jest.resetModules();
    process.env = { ...originalEnv };
    delete process.env.OPENROUTER_API_KEY;
    delete process.env.GROQ_API_KEY;
    delete process.env.OPENCODE_API_KEY;
    // 清理.env文件以避免测试间相互影响
    try {
      unlinkSync('.env');
    } catch {}
  });

  afterAll(() => {
    process.env = originalEnv;
  });

  describe('getProviderKey', () => {
    test('should return undefined when key not set', () => {
      const key = getProviderKey('openrouter');
      expect(key).toBeUndefined();
    });

    test('should return openrouter key when set', () => {
      process.env.OPENROUTER_API_KEY = 'sk-test-key';
      const key = getProviderKey('openrouter');
      expect(key).toBe('sk-test-key');
    });

    test('should return groq key when set', () => {
      process.env.GROQ_API_KEY = 'gsk-test-key';
      const key = getProviderKey('groq');
      expect(key).toBe('gsk-test-key');
    });

    test('should return opencode key when set', () => {
      process.env.OPENCODE_API_KEY = 'zen-test-key';
      const key = getProviderKey('opencode');
      expect(key).toBe('zen-test-key');
    });

    test('should return undefined for unknown provider', () => {
      const key = getProviderKey('unknown');
      expect(key).toBeUndefined();
    });

    test('should read provider key from .env when process env is empty', () => {
      writeFileSync('.env', 'GEMINI_API_KEY=AIza-file-key\n');
      delete process.env.GEMINI_API_KEY;

      const key = getProviderKey('gemini');
      expect(key).toBe('AIza-file-key');
    });
  });

  describe('saveProviderKey', () => {
    test('should save openrouter key to .env file', async () => {
      await saveProviderKey('openrouter', 'sk-test-key');
      const key = getProviderKey('openrouter');
      expect(key).toBe('sk-test-key');
    });

    test('should save groq key to .env file', async () => {
      await saveProviderKey('groq', 'gsk-test-key');
      const key = getProviderKey('groq');
      expect(key).toBe('gsk-test-key');
    });

    test('should throw error for empty key', async () => {
      await expect(saveProviderKey('openrouter', '')).rejects.toThrow('API key cannot be empty');
    });

    test('should throw error for unknown provider', async () => {
      await expect(saveProviderKey('unknown', 'test-key')).rejects.toThrow('Unknown provider');
    });
  });

  describe('getAllProviderKeysStatus', () => {
    test('should return status for all providers', async () => {
      process.env.OPENROUTER_API_KEY = 'sk-test-key';
      const status = await getAllProviderKeysStatus();
      expect(status).toHaveProperty('openrouter');
      expect(status).toHaveProperty('groq');
      expect(status).toHaveProperty('opencode');
      expect(status.openrouter.configured).toBe(true);
      expect(status.groq.configured).toBe(false);
      expect(status.opencode.configured).toBe(false);
    });

    test('should mask API keys properly', async () => {
      process.env.GROQ_API_KEY = 'gsk-abcdefghijklmn';
      const status = await getAllProviderKeysStatus();
      expect(status.groq.masked).toBe('gsk-***lmn');
    });
  });
});
