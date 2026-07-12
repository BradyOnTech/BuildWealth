import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { renderDocumentCapture, captureState } from '../views/profile/document_capture.js';
import { renderOverview } from '../views/profile/overview.js';

function resetState() {
  captureState.phase = 'idle';
  captureState.fileName = null;
  captureState.result = null;
  captureState.applied = null;
  captureState.error = null;
}

test('document capture: idle card offers an upload control and a disabled Extract', () => {
  resetState();
  const markup = String(renderDocumentCapture());
  assert.match(markup, /From a document/);
  assert.match(markup, /paystub, W-2, mortgage statement, or insurance declaration/);
  assert.match(markup, /nothing is saved until you apply/);
  assert.match(markup, /type="file"/);
  assert.match(markup, /accept="image\/\*"/);
  assert.match(markup, /data-doccap-file/);
  assert.match(markup, /data-doccap-action="extract"/);
  assert.match(markup, /disabled/);            // no file picked yet
  // No invented amounts before anything is read.
  assert.doesNotMatch(markup, /\$\d/);
});

test('document capture: ready state lists suggestions with per-section include checkboxes and Apply', () => {
  resetState();
  captureState.phase = 'ready';
  captureState.result = {
    status: 'ready',
    document_type: 'paystub',
    confidence: 'high',
    warnings: ['YTD column is blurry.'],
    suggestions: {
      income_items: [
        { label: 'Salary — Acme Corp', monthly_amount_usd: 8666.67, source_type: 'salary', is_pre_tax: false },
      ],
      tax_profile: { state: 'CO', effective_tax_rate: 0.18 },
      notes_hint: 'Pre-tax deductions were visible.',
    },
  };
  const markup = String(renderDocumentCapture());
  assert.match(markup, /Paystub/);
  assert.match(markup, /confidence high/);
  assert.match(markup, /YTD column is blurry\./);
  assert.match(markup, /Salary — Acme Corp/);
  assert.match(markup, /\$8,667\/mo|\$8,666\.67\/mo/);
  assert.match(markup, /data-doccap-include="income_items"/);
  assert.match(markup, /data-doccap-include="tax_profile"/);
  assert.match(markup, /18\.00%/);              // rate rendered as percent
  assert.match(markup, /Pre-tax deductions were visible\./);
  assert.match(markup, /data-doccap-action="apply"/);
  assert.match(markup, /data-doccap-action="reset"/);
  resetState();
});

test('document capture: empty extraction and unconfigured provider get quiet hints', () => {
  resetState();
  captureState.phase = 'ready';
  captureState.result = { status: 'ready', document_type: 'other', confidence: 'low', warnings: [], suggestions: {} };
  const empty = String(renderDocumentCapture());
  assert.match(empty, /Nothing usable was read/);
  assert.doesNotMatch(empty, /data-doccap-action="apply"/);

  captureState.phase = 'unconfigured';
  captureState.error = 'No AI provider is configured.';
  const unconfigured = String(renderDocumentCapture());
  assert.match(unconfigured, /No AI provider is configured\./);
  assert.match(unconfigured, /#settings/);
  assert.doesNotMatch(unconfigured, /data-doccap-action="apply"/);
  resetState();
});

test('document capture: applied and error states report honestly', () => {
  resetState();
  captureState.phase = 'applied';
  captureState.applied = { applied_sections: ['income_items'], counts: { income_items: 1 }, skipped_duplicates: 1 };
  const applied = String(renderDocumentCapture());
  assert.match(applied, /Applied to your profile: 1 income/);
  assert.match(applied, /1 duplicate skipped/);

  captureState.phase = 'error';
  captureState.error = 'The AI provider could not read the image.';
  const errored = String(renderDocumentCapture());
  assert.match(errored, /could not read the image/);
  assert.match(errored, /data-doccap-action="reset"/);
  resetState();
});

test('document capture: overview renders the card and re-exports it', () => {
  resetState();
  const markup = String(renderOverview({ profile: { income_items: [], expense_items: [] }, candidates: [] }));
  assert.match(markup, /id="profile-doc-capture"/);
  assert.match(markup, /From a document/);
});

test('document capture: module wires extract and apply through the api layer', () => {
  const source = readFileSync(resolve(import.meta.dirname, '../views/profile/document_capture.js'), 'utf8');
  // Extract posts the picked file; Apply sends only the sections left ticked.
  assert.match(source, /api\.profileDocumentVision\(formData\)/);
  assert.match(source, /formData\.append\('file', file\)/);
  assert.match(source, /api\.applyProfileDocumentVision\(patch\)/);
  assert.match(source, /box\.checked && suggestions\[section\]/);
  // Wiring is delegated on the card's own container — profile.js stays untouched.
  assert.match(source, /data-doccap-action/);
  assert.match(source, /getElementById\('profile-doc-capture'\)/);
  assert.doesNotMatch(source, /from '\.\.\/profile\.js'/);

  const overviewSource = readFileSync(resolve(import.meta.dirname, '../views/profile/overview.js'), 'utf8');
  assert.match(overviewSource, /renderDocumentCapture/);

  const apiSource = readFileSync(resolve(import.meta.dirname, '../lib/api.js'), 'utf8');
  assert.match(apiSource, /profileDocumentVision:\s+\(formData\) => postForm\('\/api\/profile\/document-vision', formData\)/);
  assert.match(apiSource, /applyProfileDocumentVision:\s+\(body = \{\}\) => postJson\('\/api\/profile\/document-vision\/apply', body\)/);
});
