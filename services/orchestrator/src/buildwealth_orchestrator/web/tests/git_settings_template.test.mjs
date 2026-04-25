import test from 'node:test';
import assert from 'node:assert/strict';

import { template } from '../views/settings.js';

test('settings git section is grouped into clear workflow panels', () => {
  const html = template();

  for (const label of [
    'Git Setup Guide',
    'Local History',
    'AutoGit',
    'Remote Sync',
    'Restore Preview',
  ]) {
    assert.match(html, new RegExp(label));
  }

  assert.match(html, /id="git-guided-next-step"/);
  assert.match(html, /id="preview-git-restore"/);
  assert.match(html, /id="apply-git-restore"/);
  assert.match(html, /never runs raw git checkout/);
});
