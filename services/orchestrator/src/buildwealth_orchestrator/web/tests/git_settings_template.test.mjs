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
    'Git Activity Feed',
  ]) {
    assert.match(html, new RegExp(label));
  }

  assert.match(html, /id="git-guided-next-step"/);
  assert.match(html, /id="preview-git-restore"/);
  assert.match(html, /id="git-restore-preview-rows"/);
  assert.match(html, /id="select-supported-git-restore"/);
  assert.match(html, /id="apply-git-restore"/);
  assert.match(html, /id="git-audit-feed"/);
  assert.match(html, /id="git-activity-event-type"/);
  assert.match(html, /id="git-activity-status"/);
  assert.match(html, /id="git-activity-ref"/);
  assert.match(html, /id="git-activity-search"/);
  assert.match(html, /id="git-activity-summary"/);
  assert.match(html, /id="export-git-activity-json"/);
  assert.match(html, /id="export-git-activity-csv"/);
  assert.match(html, /id="git-activity-retention-max-events"/);
  assert.match(html, /id="preview-git-activity-cleanup"/);
  assert.match(html, /id="apply-git-activity-cleanup"/);
  assert.match(html, /Run dry-run cleanup before deleting activity events/);
  assert.match(html, /survives page reloads|Recent checkpoints|Git Activity Feed/);
  assert.match(html, /never runs raw git checkout/);
});
