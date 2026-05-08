import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { renderTrustDurability } from '../views/atelier.js';

test('atelier api exposes trust and durability endpoints', () => {
  const apiSource = readFileSync(resolve(import.meta.dirname, '../lib/api.js'), 'utf8');

  assert.match(apiSource, /durableStorageStatus:\s*\(\)/);
  assert.match(apiSource, /\/api\/storage\/durable\/status/);
  assert.match(apiSource, /storageBackups:\s*\(\)/);
  assert.match(apiSource, /\/api\/storage\/backups/);
  assert.match(apiSource, /createStorageBackup:\s*\(body/);
  assert.match(apiSource, /postJson\('\/api\/storage\/backups'/);
  assert.match(apiSource, /storageProtectionStatus:\s*\(\)/);
  assert.match(apiSource, /\/api\/storage\/protection\/status/);
  assert.match(apiSource, /applyStorageProtection:\s*\(body/);
  assert.match(apiSource, /postJson\('\/api\/storage\/protection\/apply'/);
  assert.match(apiSource, /gitStatus:\s*\(\)/);
  assert.match(apiSource, /\/api\/git\/status/);
  assert.match(apiSource, /gitHistory:\s*\(limit/);
  assert.match(apiSource, /\/api\/git\/history/);
  assert.match(apiSource, /createGitCheckpoint:\s*\(body/);
  assert.match(apiSource, /postJson\('\/api\/git\/checkpoint'/);
  assert.match(apiSource, /gitRestorePreview:\s*\(opts/);
  assert.match(apiSource, /\/api\/git\/restore-preview/);
  assert.match(apiSource, /gitActivity:\s*\(/);
  assert.match(apiSource, /\/api\/git\/activity/);
  assert.match(apiSource, /releaseReadiness:\s*\(\)/);
  assert.match(apiSource, /\/api\/release-readiness/);
  assert.match(apiSource, /recordReleaseWorkflowVerification:\s*\(/);
  assert.match(apiSource, /\/api\/release-readiness\/workflow-verification/);
});

test('atelier renders trust durability visibility from existing status payloads', () => {
  const markup = String(renderTrustDurability({
    durable: {
      database_exists: true,
      document_count: 12,
      latest_rollback_check_passed: true,
      latest_migration_at: '2026-04-30T12:00:00Z',
    },
    backups: {
      backups: [
        {
          backup_id: '20260430T120000Z',
          created_at: '2026-04-30T12:00:00Z',
          size_bytes: 2048,
        },
      ],
    },
    protection: {
      supported: true,
      total_non_compliant_files: 2,
      total_non_compliant_directories: 1,
      policy: {
        protection_level: 'standard',
        last_applied_at: null,
      },
    },
    git: {
      status: 'ok',
      dirty: true,
      changed_files: [{ path: 'plans/plan.md', status: 'M' }],
      last_commit: null,
      has_remote: false,
    },
    activity: {
      summary: {
        total_matched: 3,
      },
      events: [
        {
          id: 'audit-profile',
          created_at: '2026-04-30T12:00:00Z',
          event_type: 'profile_update',
          title: 'Financial profile updated',
          message: 'Updated tax profile.',
          status: 'ok',
          metadata: { sections: ['tax_profile'], source: 'manual_api' },
        },
        {
          id: 'audit-copilot',
          created_at: '2026-04-30T12:05:00Z',
          event_type: 'copilot_profile_update',
          title: 'Copilot profile update applied',
          message: 'Applied reviewed Copilot profile draft.',
          status: 'ok',
          metadata: { sections: ['investment_policy'], source: 'copilot_profile_draft' },
        },
      ],
    },
    readiness: {
      status: 'blocked',
      ready_count: 4,
      total_count: 8,
      summary: 'Release readiness is blocked by trust or provider gaps.',
      blocking_gaps: ['No local backup archive is available.'],
      warnings: ['3 protection item(s) need attention.'],
      checks: [
        {
          id: 'backup',
          title: 'Backup available',
          status: 'blocked',
          detail: 'No local backup archive is available.',
          domain: 'storage',
          action_kind: 'create_backup',
        },
        {
          id: 'protection',
          title: 'Protection compliant',
          status: 'warning',
          detail: '3 protection item(s) need attention.',
          domain: 'protection',
          action_kind: 'apply_protection',
        },
        {
          id: 'providers',
          title: 'Provider and engine health',
          status: 'blocked',
          detail: 'Provider/engine degradation is present: ignidash_scenario.',
          domain: 'provider',
          action_kind: 'review_provider_status',
        },
      ],
      recommended_actions: [
        {
          action_kind: 'create_backup',
          label: 'Create backup',
          detail: 'Create a local backup before relying on today’s app state.',
          href: '#atelier?section=trust',
        },
      ],
    },
  }));

  assert.match(markup, /Trust &amp; durability/);
  assert.match(markup, /Needs review/);
  assert.match(markup, /Latest backup/);
  assert.match(markup, /20260430T120000Z/);
  assert.match(markup, /Protection/);
  assert.match(markup, /3 issue/);
  assert.match(markup, /Git checkpoints/);
  assert.match(markup, /1 uncheckpointed/);
  assert.match(markup, /Audit events/);
  assert.match(markup, /3/);
  assert.match(markup, /data-trust-action="create-backup"/);
  assert.match(markup, /data-trust-action="apply-protection"/);
  assert.match(markup, /data-trust-action="create-checkpoint"/);
  assert.match(markup, /data-trust-action="preview-restore"/);
  assert.match(markup, /id="trust-restore-ref"/);
  assert.match(markup, /Ready to rely today\?/);
  assert.match(markup, /4\/8 checks ready/);
  assert.match(markup, /Release readiness is blocked/);
  assert.match(markup, /Provider and engine health/);
  assert.match(markup, /Create backup/);
  assert.match(markup, /Backup available/);
  assert.match(markup, /Protection compliant/);
  assert.match(markup, /Profile &amp; Copilot changes/);
  assert.match(markup, /Financial profile updated/);
  assert.match(markup, /Copilot profile update applied/);
  assert.match(markup, /tax profile/);
  assert.match(markup, /investment policy/);
  assert.match(markup, /href="\/classic#settings"/);
});

test('atelier renders read-only restore preview details', () => {
  const markup = String(renderTrustDurability({
    restorePreview: {
      status: 'ok',
      message: 'Read-only restore preview generated. No files were changed.',
      ref: 'abc123',
      read_only: true,
      total_files: 1,
      files: [
        {
          path: 'plans/plan.md',
          status: 'modified',
          diff: '- old\n+ new',
          truncated: false,
        },
      ],
      warnings: ['Preview only.'],
    },
  }));

  assert.match(markup, /Read-only restore preview/);
  assert.match(markup, /No files were changed/);
  assert.match(markup, /plans\/plan\.md/);
  assert.match(markup, /Preview only\./);
  assert.doesNotMatch(markup, /restore-apply/);
});
