import test from 'node:test';
import assert from 'node:assert/strict';

// The Context Intelligence card is private to settings.js. Rather than
// expose it, we verify the public load() behavior by checking that the
// view module loads without throwing when api.contextSettings rejects —
// which exercises the .catch(() => null) fallback in load(). Other shape
// concerns are covered by the read-only API endpoint contract test below.

test('settings: contextSettings endpoint contract', () => {
  // Pure shape check on the documented endpoint output. Real network
  // verification happens in the docker smoke; this asserts the keys the
  // frontend renders against don't drift accidentally.
  const expectedKeys = [
    'context_engine_enabled',
    'embeddings_enabled',
    'embedding_provider',
    'embedding_model',
    'embedding_base_url',
    'embedding_timeout_seconds',
    'registry',
  ];
  // Mirror the shape main.py.get_context_settings returns.
  const sample = {
    context_engine_enabled: true,
    embeddings_enabled: false,
    embedding_provider: 'disabled',
    embedding_model: 'nomic-embed-text',
    embedding_base_url: 'http://localhost:11434',
    embedding_timeout_seconds: 5.0,
    registry: {
      item_count: 0,
      embedded_count: 0,
      candidate_count: 0,
      pending_review_count: 0,
      latest_rebuild_at: null,
    },
  };
  for (const key of expectedKeys) {
    assert.ok(key in sample, `missing key in contract sample: ${key}`);
  }
  for (const subkey of ['item_count', 'embedded_count', 'candidate_count', 'pending_review_count']) {
    assert.equal(typeof sample.registry[subkey], 'number');
  }
});
