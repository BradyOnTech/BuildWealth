import test from 'node:test';
import assert from 'node:assert/strict';

import { collectPlanSettingsPayload, setPlanSettingsInputs } from '../lib/components.js';
import { DIFF_SETTING_VALUE_FIELDS, PLAN_SETTING_VALUE_FIELDS } from '../lib/plan_setting_fields.js';

function makeInputMap(fields) {
  const entries = fields.map((field) => [field.inputId, { value: '' }]);
  return new Map(entries);
}

function getInputById(map) {
  return (inputId) => map.get(inputId) || null;
}

function seedFieldInputs(fields) {
  const map = makeInputMap(fields);
  for (let index = 0; index < fields.length; index += 1) {
    const field = fields[index];
    const input = map.get(field.inputId);
    if (!input) continue;
    if (field.kind === 'select') {
      const options = Array.isArray(field.options) ? field.options : [];
      const choice = options[Math.min(1, Math.max(0, options.length - 1))];
      input.value = String(choice?.value || '');
      continue;
    }
    const min = typeof field.min === 'number' ? field.min : 0;
    const max = typeof field.max === 'number' ? field.max : null;
    let value = field.integer ? Math.max(min, index + 1) : Math.max(min, (index + 1) * 1.25);
    if (typeof max === 'number') value = Math.min(max, value);
    input.value = field.integer ? String(Math.trunc(value)) : String(Number(value.toFixed(4)));
  }
  return map;
}

function assertRoundTrip(fields) {
  const seededInputs = seedFieldInputs(fields);
  const payload = collectPlanSettingsPayload(
    fields,
    { includeNulls: true, getInputById: getInputById(seededInputs) },
  );

  const hydratedInputs = makeInputMap(fields);
  setPlanSettingsInputs(
    fields,
    payload,
    { getInputById: getInputById(hydratedInputs) },
  );
  const roundTrippedPayload = collectPlanSettingsPayload(
    fields,
    { includeNulls: true, getInputById: getInputById(hydratedInputs) },
  );
  assert.deepEqual(roundTrippedPayload, payload);
}

test('plan-setting registry round-trips base settings', () => {
  assertRoundTrip(PLAN_SETTING_VALUE_FIELDS);
});

test('plan-setting registry round-trips diff overrides', () => {
  assertRoundTrip(DIFF_SETTING_VALUE_FIELDS);
});
