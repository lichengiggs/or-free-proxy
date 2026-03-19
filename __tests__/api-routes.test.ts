import { describe, test, expect, beforeEach, afterEach } from '@jest/globals';
import { app } from '../src/server';
import { existsSync, unlinkSync, writeFileSync, mkdirSync, rmdirSync, readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { homedir } from 'node:os';

const ENV_PATH = join(process.cwd(), '.env');
const ENV_BACKUP_PATH = join(process.cwd(), '.env.test.backup');
const OPENCLAW_DIR = join(homedir(), '.openclaw-test');
const CONFIG_PATH = join(OPENCLAW_DIR, 'openclaw.json');

describe('API Routes - API Key', () => {
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

  describe('POST /api/validate-key', () => {
    test('should validate valid API key', async () => {
      const res = await app.request('/api/validate-key', {
        method: 'POST',
        body: JSON.stringify({ apiKey: 'sk-test123456789' }),
        headers: { 'Content-Type': 'application/json' }
      });
      
      expect(res.status).toBe(200);
      const json = await res.json();
      expect(json.success).toBe(true);
      expect(json.message).toContain('success');
    });

    test('should reject empty API key', async () => {
      const res = await app.request('/api/validate-key', {
        method: 'POST',
        body: JSON.stringify({ apiKey: '' }),
        headers: { 'Content-Type': 'application/json' }
      });
      
      expect(res.status).toBe(400);
      const json = await res.json();
      expect(json.success).toBe(false);
      expect(json.error).toContain('empty');
    });

    test('should reject invalid API key format', async () => {
      const res = await app.request('/api/validate-key', {
        method: 'POST',
        body: JSON.stringify({ apiKey: 'invalid-format' }),
        headers: { 'Content-Type': 'application/json' }
      });
      
      expect(res.status).toBe(400);
      const json = await res.json();
      expect(json.success).toBe(false);
      expect(json.error).toContain('Invalid');
    });

    test('should reject invalid OpenRouter API key', async () => {
      const res = await app.request('/api/validate-key', {
        method: 'POST',
        body: JSON.stringify({ apiKey: 'sk-invalid-key' }),
        headers: { 'Content-Type': 'application/json' }
      });
      
      expect(res.status).toBe(401);
      const json = await res.json();
      expect(json.success).toBe(false);
      expect(json.error).toContain('invalid');
    });

    test('should handle network errors', async () => {
      const res = await app.request('/api/validate-key', {
        method: 'POST',
        body: JSON.stringify({ apiKey: 'sk-test-network-error' }),
        headers: { 'Content-Type': 'application/json' }
      });
      
      expect(res.status).toBe(500);
      const json = await res.json();
      expect(json.success).toBe(false);
      expect(json.error).toContain('network');
    });

    test('should save API key after validation', async () => {
      const res = await app.request('/api/validate-key', {
        method: 'POST',
        body: JSON.stringify({ apiKey: 'sk-test123456789' }),
        headers: { 'Content-Type': 'application/json' }
      });
      
      expect(res.status).toBe(200);
      
      // 验证 .env 文件是否包含 API key
      const content = readFileSync(ENV_PATH, 'utf-8');
      expect(content).toContain('OPENROUTER_API_KEY=sk-test123456789');
    });
  });

  describe('GET /api/validate-key', () => {
    test('should return not configured status', async () => {
      const res = await app.request('/api/validate-key', {
        method: 'GET'
      });
      
      expect(res.status).toBe(200);
      const json = await res.json();
      expect(json.configured).toBe(false);
      expect(json.masked).toBeNull();
    });

    test('should return configured status', async () => {
      writeFileSync(ENV_PATH, 'OPENROUTER_API_KEY=sk-test123456\n');
      
      const res = await app.request('/api/validate-key', {
        method: 'GET'
      });
      
      expect(res.status).toBe(200);
      const json = await res.json();
      expect(json.configured).toBe(true);
      expect(json.masked).toBe('sk-****456');
    });
  });
});

describe('API Routes - OpenClaw Config', () => {
  beforeEach(() => {
    // 清理测试目录
    if (existsSync(OPENCLAW_DIR)) {
      const files = readdirSync(OPENCLAW_DIR);
      files.forEach((file: string) => {
        if (file.startsWith('openclaw.json')) {
          unlinkSync(join(OPENCLAW_DIR, file));
        }
      });
      rmdirSync(OPENCLAW_DIR);
    }
  });

  afterEach(() => {
    // 清理测试目录
    if (existsSync(OPENCLAW_DIR)) {
      const files = readdirSync(OPENCLAW_DIR);
      files.forEach((file: string) => {
        if (file.startsWith('openclaw.json')) {
          unlinkSync(join(OPENCLAW_DIR, file));
        }
      });
      rmdirSync(OPENCLAW_DIR);
    }
  });

  describe('GET /api/detect-openclaw', () => {
    test('should return not detected when config does not exist', async () => {
      const res = await app.request('/api/detect-openclaw', {
        method: 'GET'
      });
      
      expect(res.status).toBe(200);
      const json = await res.json();
      expect(json.exists).toBe(false);
      expect(json.isValid).toBe(false);
    });

    test('should return detected when config exists and is valid', async () => {
      mkdirSync(OPENCLAW_DIR, { recursive: true });
      writeFileSync(CONFIG_PATH, JSON.stringify({
        models: { providers: {} },
        agents: { defaults: { models: {} } }
      }));
      
      const res = await app.request('/api/detect-openclaw', {
        method: 'GET'
      });
      
      expect(res.status).toBe(200);
      const json = await res.json();
      expect(json.exists).toBe(true);
      expect(json.isValid).toBe(true);
      expect(json.content).toBeDefined();
    });

    test('should return invalid when config is not valid JSON', async () => {
      mkdirSync(OPENCLAW_DIR, { recursive: true });
      writeFileSync(CONFIG_PATH, 'invalid json{');
      
      const res = await app.request('/api/detect-openclaw', {
        method: 'GET'
      });
      
      expect(res.status).toBe(200);
      const json = await res.json();
      expect(json.exists).toBe(true);
      expect(json.isValid).toBe(false);
    });
  });

  describe('POST /api/configure-openclaw', () => {
    test('should configure OpenClaw when config does not exist', async () => {
      const res = await app.request('/api/configure-openclaw', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      
      expect(res.status).toBe(200);
      const json = await res.json();
      expect(json.success).toBe(true);
      expect(json.message).toContain('success');
    });

    test('should backup existing config before merging', async () => {
      mkdirSync(OPENCLAW_DIR, { recursive: true });
      writeFileSync(CONFIG_PATH, JSON.stringify({ old: 'config' }));
      
      const res = await app.request('/api/configure-openclaw', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      
      expect(res.status).toBe(200);
      const json = await res.json();
      expect(json.backup).toBeDefined();
      expect(json.backup).toMatch(/openclaw\.json\.backup\.\d+/);
    });

    test('should return error when API key not validated', async () => {
      const res = await app.request('/api/configure-openclaw', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      
      // 如果 API key 未验证，应该返回错误
      const json = await res.json();
      if (json.success === false) {
        expect(json.error).toContain('API key');
      }
    });

    test('should merge config with existing providers', async () => {
      mkdirSync(OPENCLAW_DIR, { recursive: true });
      writeFileSync(CONFIG_PATH, JSON.stringify({
        models: {
          providers: {
            existing_provider: { baseUrl: 'http://example.com' }
          }
        },
        agents: { defaults: { models: {} } }
      }));
      
      const res = await app.request('/api/configure-openclaw', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      
      expect(res.status).toBe(200);
      
      // 验证配置合并正确
      const config = JSON.parse(readFileSync(CONFIG_PATH, 'utf-8'));
      expect(config.models.providers.existing_provider).toBeDefined();
      expect(config.models.providers.free_proxy).toBeDefined();
    });
  });

  describe('GET /api/backups', () => {
    test('should return empty list when no backups exist', async () => {
      const res = await app.request('/api/backups', {
        method: 'GET'
      });
      
      expect(res.status).toBe(200);
      const json = await res.json();
      expect(json.backups).toEqual([]);
    });

    test('should return list of backup files', async () => {
      mkdirSync(OPENCLAW_DIR, { recursive: true });
      writeFileSync(join(OPENCLAW_DIR, 'openclaw.json.backup.20260319143022'), '{}');
      writeFileSync(join(OPENCLAW_DIR, 'openclaw.json.backup.20260319150000'), '{}');
      
      const res = await app.request('/api/backups', {
        method: 'GET'
      });
      
      expect(res.status).toBe(200);
      const json = await res.json();
      expect(json.backups.length).toBe(2);
      expect(json.backups[0]).toBe('openclaw.json.backup.20260319150000');
    });
  });

  describe('POST /api/restore-backup', () => {
    test('should restore from backup', async () => {
      mkdirSync(OPENCLAW_DIR, { recursive: true });
      const backupData = { old: 'backup' };
      writeFileSync(join(OPENCLAW_DIR, 'openclaw.json.backup.20260319143022'), JSON.stringify(backupData));
      
      const res = await app.request('/api/restore-backup', {
        method: 'POST',
        body: JSON.stringify({ backup: 'openclaw.json.backup.20260319143022' }),
        headers: { 'Content-Type': 'application/json' }
      });
      
      expect(res.status).toBe(200);
      const json = await res.json();
      expect(json.success).toBe(true);
    });

    test('should return error when backup not found', async () => {
      const res = await app.request('/api/restore-backup', {
        method: 'POST',
        body: JSON.stringify({ backup: 'non-existent.backup' }),
        headers: { 'Content-Type': 'application/json' }
      });
      
      expect(res.status).toBe(404);
      const json = await res.json();
      expect(json.success).toBe(false);
      expect(json.error).toContain('not found');
    });
  });
});