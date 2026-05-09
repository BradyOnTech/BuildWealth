import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

test('workflows page exposes native tuning, preview, and save-to-plan controls', () => {
  const source = readFileSync(resolve(import.meta.dirname, '../views/workflows.js'), 'utf8');

  assert.match(source, /Tune the inputs/);
  assert.match(source, /Save report to plan/);
  assert.match(source, /workflow-result-preview/);
  assert.match(source, /plan_id/);
  assert.match(source, /params: options\.params/);
  assert.match(source, /save_to_plan: options\.saveToPlan/);
  assert.doesNotMatch(source, /classic/i);
  assert.doesNotMatch(source, /\/classic/);
});
