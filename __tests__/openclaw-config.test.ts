import { describe, test, expect, beforeEach, afterEach } from '@jest/globals';
import { existsSync, writeFileSync, rmSync, readFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';

const OPENCLAW_DIR = join(process.cwd(), '.openclaw-test-local');
const CONFIG_PATH = join(OPENCLAW_DIR, 'openclaw.json');

describe('OpenClaw Config', () => {
  beforeEach(() => {
    process.env.OPENCLAW_TEST_DIR = OPENCLAW_DIR;
    if (existsSync(OPENCLAW_DIR)) {
      rmSync(OPENCLAW_DIR, { recursive: true, force: true });
    }
  });

  afterEach(() => {
    if (existsSync(OPENCLAW_DIR)) {
      rmSync(OPENCLAW_DIR, { recursive: true, force: true });
    }
    delete process.env.OPENCLAW_TEST_DIR;
  });

  test('detectOpenClawConfig should return not exists initially', async () => {
    const { detectOpenClawConfig } = await import('../src/openclaw-config');
    const result = await detectOpenClawConfig();
    expect(result.exists).toBe(false);
    expect(result.isValid).toBe(false);
  });

  test('mergeConfig should create config and provider entries', async () => {
    const { mergeConfig } = await import('../src/openclaw-config');
    const result = await mergeConfig();
    expect(result.success).toBe(true);
    expect(existsSync(CONFIG_PATH)).toBe(true);

    const config = JSON.parse(readFileSync(CONFIG_PATH, 'utf-8'));
    expect(config.models.providers.free_proxy).toBeDefined();
    expect(config.agents.defaults.models['free_proxy/auto']).toBeDefined();
  });

  test('mergeConfig should create backup when config exists', async () => {
    const { mergeConfig } = await import('../src/openclaw-config');
    mkdirSync(OPENCLAW_DIR, { recursive: true });
    writeFileSync(CONFIG_PATH, JSON.stringify({ foo: 'bar' }));

    const result = await mergeConfig();
    expect(result.success).toBe(true);
    expect(result.backup).toBeDefined();
    expect(String(result.backup)).toMatch(/openclaw\.bak\d+/);
  });

  test('listBackups should list created backups', async () => {
    const { listBackups } = await import('../src/openclaw-config');
    mkdirSync(OPENCLAW_DIR, { recursive: true });
    writeFileSync(join(OPENCLAW_DIR, 'openclaw.bak1'), '{}');
    writeFileSync(join(OPENCLAW_DIR, 'openclaw.bak2'), '{}');

    const backups = await listBackups();
    expect(backups).toEqual(['openclaw.bak2', 'openclaw.bak1']);
  });

  test('restoreBackup should restore valid backup', async () => {
    const { restoreBackup } = await import('../src/openclaw-config');
    mkdirSync(OPENCLAW_DIR, { recursive: true });
    const payload = { hello: 'world' };
    writeFileSync(join(OPENCLAW_DIR, 'openclaw.bak1'), JSON.stringify(payload));

    const restored = await restoreBackup('openclaw.bak1');
    expect(restored.success).toBe(true);

    const content = JSON.parse(readFileSync(CONFIG_PATH, 'utf-8'));
    expect(content).toEqual(payload);
  });
});
