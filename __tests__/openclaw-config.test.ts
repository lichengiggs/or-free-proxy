import { describe, test, expect, beforeEach, afterEach } from '@jest/globals';
import { 
  detectOpenClawConfig, 
  mergeConfig, 
  listBackups, 
  restoreBackup 
} from '../src/openclaw-config';
import { existsSync, unlinkSync, writeFileSync, mkdirSync, rmdirSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { homedir } from 'node:os';

const OPENCLAW_DIR = join(homedir(), '.openclaw-test');
const CONFIG_PATH = join(OPENCLAW_DIR, 'openclaw.json');

describe('OpenClaw Config', () => {
  beforeEach(() => {
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

  describe('detectOpenClawConfig', () => {
    test('should return not exists when config file does not exist', async () => {
      const result = await detectOpenClawConfig();
      
      expect(result.exists).toBe(false);
      expect(result.isValid).toBe(false);
    });

    test('should return exists and valid when config file is valid JSON', async () => {
      mkdirSync(OPENCLAW_DIR, { recursive: true });
      writeFileSync(CONFIG_PATH, JSON.stringify({
        models: { providers: {} },
        agents: { defaults: { models: {} } }
      }));
      
      const result = await detectOpenClawConfig();
      
      expect(result.exists).toBe(true);
      expect(result.isValid).toBe(true);
      expect(result.content).toBeDefined();
    });

    test('should return exists but invalid when config file is invalid JSON', async () => {
      mkdirSync(OPENCLAW_DIR, { recursive: true });
      writeFileSync(CONFIG_PATH, 'invalid json{');
      
      const result = await detectOpenClawConfig();
      
      expect(result.exists).toBe(true);
      expect(result.isValid).toBe(false);
    });

    test('should return content when config exists', async () => {
      const configData = {
        models: { providers: { test: {} } },
        agents: { defaults: { models: {} } }
      };
      mkdirSync(OPENCLAW_DIR, { recursive: true });
      writeFileSync(CONFIG_PATH, JSON.stringify(configData));
      
      const result = await detectOpenClawConfig();
      
      expect(result.content).toEqual(configData);
    });
  });

  describe('mergeConfig', () => {
    test('should create new config if not exists', async () => {
      const result = await mergeConfig();
      
      expect(result.success).toBe(true);
      expect(result.backup).toBeNull(); // 新文件不需要备份
      
      // 验证配置文件已创建
      expect(existsSync(CONFIG_PATH)).toBe(true);
      
      // 验证配置内容
      const config = JSON.parse(readFileSync(CONFIG_PATH, 'utf-8'));
      expect(config.models.providers.free_proxy).toBeDefined();
      expect(config.models.providers.free_proxy.baseUrl).toBe('http://localhost:8765/v1');
      expect(config.agents.defaults.models['free_proxy/auto']).toBeDefined();
    });

    test('should merge with existing config', async () => {
      mkdirSync(OPENCLAW_DIR, { recursive: true });
      const existingConfig = {
        models: {
          providers: {
            existing_provider: { baseUrl: 'http://example.com' }
          }
        },
        agents: {
          defaults: {
            models: {
              'existing/model': {}
            }
          }
        }
      };
      writeFileSync(CONFIG_PATH, JSON.stringify(existingConfig));
      
      const result = await mergeConfig();
      
      expect(result.success).toBe(true);
      expect(result.backup).toBeDefined();
      
      const config = JSON.parse(readFileSync(CONFIG_PATH, 'utf-8'));
      
      // 验证原有配置保留
      expect(config.models.providers.existing_provider).toBeDefined();
      expect(config.agents.defaults.models['existing/model']).toBeDefined();
      
      // 验证新配置添加
      expect(config.models.providers.free_proxy).toBeDefined();
      expect(config.agents.defaults.models['free_proxy/auto']).toBeDefined();
    });

    test('should overwrite existing free_proxy provider', async () => {
      mkdirSync(OPENCLAW_DIR, { recursive: true });
      const existingConfig = {
        models: {
          providers: {
            free_proxy: { baseUrl: 'http://old-url.com' }
          }
        },
        agents: { defaults: { models: {} } }
      };
      writeFileSync(CONFIG_PATH, JSON.stringify(existingConfig));
      
      const result = await mergeConfig();
      
      expect(result.success).toBe(true);
      
      const config = JSON.parse(readFileSync(CONFIG_PATH, 'utf-8'));
      expect(config.models.providers.free_proxy.baseUrl).toBe('http://localhost:8765/v1');
    });

    test('should not modify default model configuration', async () => {
      mkdirSync(OPENCLAW_DIR, { recursive: true });
      const existingConfig = {
        models: { providers: {} },
        agents: {
          defaults: {
            model: { primary: 'existing/model' },
            models: {}
          }
        }
      };
      writeFileSync(CONFIG_PATH, JSON.stringify(existingConfig));
      
      await mergeConfig();
      
      const config = JSON.parse(readFileSync(CONFIG_PATH, 'utf-8'));
      expect(config.agents.defaults.model.primary).toBe('existing/model');
    });

    test('should create backup file', async () => {
      mkdirSync(OPENCLAW_DIR, { recursive: true });
      writeFileSync(CONFIG_PATH, JSON.stringify({ old: 'config' }));
      
      const result = await mergeConfig();
      
      expect(result.backup).toBeDefined();
      expect(result.backup).toMatch(/openclaw\.json\.backup\.\d+/);
      expect(existsSync(join(OPENCLAW_DIR, result.backup!))).toBe(true);
    });

    test('should return error for invalid JSON', async () => {
      mkdirSync(OPENCLAW_DIR, { recursive: true });
      writeFileSync(CONFIG_PATH, 'invalid json{');
      
      const result = await mergeConfig();
      
      expect(result.success).toBe(false);
      expect(result.error).toContain('Invalid JSON');
    });
  });

  describe('listBackups', () => {
    test('should return empty array when no backups exist', async () => {
      const backups = await listBackups();
      expect(backups).toEqual([]);
    });

    test('should return list of backup files', async () => {
      mkdirSync(OPENCLAW_DIR, { recursive: true });
      writeFileSync(join(OPENCLAW_DIR, 'openclaw.json.backup.20260319143022'), '{}');
      writeFileSync(join(OPENCLAW_DIR, 'openclaw.json.backup.20260319150000'), '{}');
      
      const backups = await listBackups();
      
      expect(backups.length).toBe(2);
      expect(backups[0]).toBe('openclaw.json.backup.20260319150000'); // 最新的在前
    });

    test('should only list backup files matching pattern', async () => {
      mkdirSync(OPENCLAW_DIR, { recursive: true });
      writeFileSync(join(OPENCLAW_DIR, 'openclaw.json.backup.20260319143022'), '{}');
      writeFileSync(join(OPENCLAW_DIR, 'other-file.txt'), 'text');
      
      const backups = await listBackups();
      
      expect(backups.length).toBe(1);
      expect(backups[0]).toBe('openclaw.json.backup.20260319143022');
    });
  });

  describe('restoreBackup', () => {
    test('should restore from backup file', async () => {
      mkdirSync(OPENCLAW_DIR, { recursive: true });
      
      const backupData = { old: 'backup' };
      writeFileSync(join(OPENCLAW_DIR, 'openclaw.json.backup.20260319143022'), JSON.stringify(backupData));
      
      const result = await restoreBackup('openclaw.json.backup.20260319143022');
      
      expect(result.success).toBe(true);
      
      const config = JSON.parse(readFileSync(CONFIG_PATH, 'utf-8'));
      expect(config).toEqual(backupData);
    });

    test('should return error when backup file does not exist', async () => {
      const result = await restoreBackup('non-existent.backup');
      
      expect(result.success).toBe(false);
      expect(result.error).toContain('Backup file not found');
    });

    test('should return error when backup file is invalid JSON', async () => {
      mkdirSync(OPENCLAW_DIR, { recursive: true });
      writeFileSync(join(OPENCLAW_DIR, 'openclaw.json.backup.20260319143022'), 'invalid json{');
      
      const result = await restoreBackup('openclaw.json.backup.20260319143022');
      
      expect(result.success).toBe(false);
      expect(result.error).toContain('Invalid JSON');
    });
  });
});