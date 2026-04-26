import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

test('inbox newest sort control uses backend created_at sort value', () => {
  const currentDir = dirname(fileURLToPath(import.meta.url));
  const source = readFileSync(resolve(currentDir, '../views/inbox.js'), 'utf8');

  assert.match(source, /data-sort="created_at"/);
  assert.doesNotMatch(source, /data-sort="newest"/);
});
