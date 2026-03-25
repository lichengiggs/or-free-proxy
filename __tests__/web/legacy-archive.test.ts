import { existsSync, readFileSync } from 'node:fs';

describe('python-mainline archive guard', () => {
  test('typescript legacy doc exists and marks TS as reference only', () => {
    const path = 'docs/typescript-legacy.md';
    expect(existsSync(path)).toBe(true);

    const content = readFileSync(path, 'utf-8');
    expect(content).toContain('仅供参考');
    expect(content).toContain('Python');
    expect(content).toContain('src/server.ts');
  });
});
