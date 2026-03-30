import { existsSync, readFileSync } from 'node:fs';

describe('python-mainline archive guard', () => {
  test('research doc is the single long-lived architecture overview', () => {
    const path = 'docs/research.md';
    expect(existsSync(path)).toBe(true);

    const content = readFileSync(path, 'utf-8');
    expect(content).toContain('当前唯一运行主线');
    expect(content).toContain('docs/research.md');
    expect(content).not.toContain('docs/typescript-legacy.md');
    expect(existsSync('docs/typescript-legacy.md')).toBe(false);
  });
});
