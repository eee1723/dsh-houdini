import { readdirSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const testsDir = path.join(here, 'tests');
const tests = readdirSync(testsDir)
  .filter((name) => name.endsWith('.test.mjs'))
  .sort();

for (const name of tests) {
  const result = spawnSync(process.execPath, [path.join(testsDir, name)], {
    cwd: path.dirname(here),
    stdio: 'inherit',
  });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}

console.log(`node test suite passed (${tests.length} files)`);
