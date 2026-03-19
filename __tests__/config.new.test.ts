import { describe, test, expect, beforeEach, afterEach } from '@jest/globals';
import { saveApiKey, getApiKeyStatus, maskApiKey } from '../src/config';
import { existsSync, unlinkSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { execSync } from 'node:child_process';

const ENV_PATH = join(process.cwd(), '.env');
const ENV_BACKUP_PATH = join(process.cwd(), '.env.test.backup');

describe('Config - API Key Management', () => {
  beforeEach(() => {
    // 备份现有 .env 文件
    if (existsSync(ENV_PATH)) {
      const content = readFileSync(ENV_PATH, 'utf-8');
      writeFileSync(ENV_BACKUP_PATH, content);
      unlinkSync(ENV_PATH);
    }
  });

  afterEach(() => {
    // 恢复备份
    if (existsSync(ENV_BACKUP_PATH)) {
      const content = readFileSync(ENV_BACKUP_PATH, 'utf-8');
      writeFileSync(ENV_PATH, content);
      unlinkSync(ENV_BACKUP_PATH);
    } else if (existsSync(ENV_PATH)) {
      unlinkSync(ENV_PATH);
    }
  });

  describe('saveApiKey', () => {
    test('should create .env file if not exists', async () => {
      expect(existsSync(ENV_PATH)).toBe(false);
      
      await saveApiKey('sk-test123456');
      
      expect(existsSync(ENV_PATH)).toBe(true);
    });

    test('should save API key to .env file', async () => {
      await saveApiKey('sk-test123456');
      
      const content = readFileSync(ENV_PATH, 'utf-8');
      expect(content).toContain('OPENROUTER_API_KEY=sk-test123456');
    });

    test('should append API key to existing .env file', async () => {
      writeFileSync(ENV_PATH, 'PORT=8765\n');
      
      await saveApiKey('sk-test123456');
      
      const content = readFileSync(ENV_PATH, 'utf-8');
      expect(content).toContain('PORT=8765');
      expect(content).toContain('OPENROUTER_API_KEY=sk-test123456');
    });

    test('should update existing API key in .env file', async () => {
      writeFileSync(ENV_PATH, 'OPENROUTER_API_KEY=old-key\n');
      
      await saveApiKey('sk-newkey123');
      
      const content = readFileSync(ENV_PATH, 'utf-8');
      expect(content).toContain('OPENROUTER_API_KEY=sk-newkey123');
      expect(content).not.toContain('old-key');
    });

    test('should set .env file permissions to 600', async () => {
      await saveApiKey('sk-test123456');
      
      // 在 Windows 上跳过权限检查
      if (process.platform !== 'win32') {
        const stats = execSync(`stat -f "%Lp" "${ENV_PATH}"`, { encoding: 'utf-8' }).trim();
        expect(stats).toBe('600');
      }
    });

    test('should reject empty API key', async () => {
      await expect(saveApiKey('')).rejects.toThrow('API key cannot be empty');
    });

    test('should reject invalid API key format', async () => {
      await expect(saveApiKey('invalid-key')).rejects.toThrow('Invalid API key format');
    });
  });

  describe('getApiKeyStatus', () => {
    test('should return "not_configured" when .env does not exist', async () => {
      const status = await getApiKeyStatus();
      
      expect(status).toEqual({
        configured: false,
        masked: null
      });
    });

    test('should return "configured" when API key exists', async () => {
      writeFileSync(ENV_PATH, 'OPENROUTER_API_KEY=sk-test123456\n');
      
      const status = await getApiKeyStatus();
      
      expect(status).toEqual({
        configured: true,
        masked: 'sk-****456'
      });
    });

    test('should return "not_configured" when .env exists but no API key', async () => {
      writeFileSync(ENV_PATH, 'PORT=8765\n');
      
      const status = await getApiKeyStatus();
      
      expect(status).toEqual({
        configured: false,
        masked: null
      });
    });
  });

  describe('maskApiKey', () => {
    test('should mask API key correctly', () => {
      const result = maskApiKey('sk-test123456789');
      expect(result).toBe('sk-****789');
    });

    test('should handle short API keys', () => {
      const result = maskApiKey('sk-abc');
      expect(result).toBe('sk-****abc');
    });

    test('should return null for empty input', () => {
      const result = maskApiKey('');
      expect(result).toBeNull();
    });

    test('should return null for null input', () => {
      const result = maskApiKey(null as any);
      expect(result).toBeNull();
    });
  });
});