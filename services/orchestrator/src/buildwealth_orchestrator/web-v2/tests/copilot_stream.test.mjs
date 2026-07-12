import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const storage = new Map();
globalThis.window = globalThis.window || {
  sessionStorage: {
    getItem: key => storage.get(key) || '',
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: key => storage.delete(key),
  },
};

const { parseSseChunk } = await import('../lib/api.js');

test('parseSseChunk parses complete data lines and buffers partials', () => {
  const events = [];
  let buffer = parseSseChunk('', 'data: {"type":"stage","stage":"thinking"}\n\ndata: {"ty', e => events.push(e));
  assert.deepEqual(events, [{ type: 'stage', stage: 'thinking' }]);
  assert.equal(buffer, 'data: {"ty');

  buffer = parseSseChunk(buffer, 'pe":"answer_delta","text":"hi"}\n', e => events.push(e));
  assert.deepEqual(events[1], { type: 'answer_delta', text: 'hi' });
  assert.equal(buffer, '');
});

test('parseSseChunk ignores comments, blank lines, and malformed JSON', () => {
  const events = [];
  const buffer = parseSseChunk(
    '',
    ': keepalive\n\ndata: not-json\ndata: {"type":"result","data":{"answer":"ok"}}\n',
    e => events.push(e),
  );
  assert.equal(buffer, '');
  assert.deepEqual(events, [{ type: 'result', data: { answer: 'ok' } }]);
});

test('copilot view streams via the SSE endpoint with cancel + banner error wiring', () => {
  const source = readFileSync(resolve(import.meta.dirname, '../views/copilot.js'), 'utf8');
  assert.match(source, /copilotChatStream/, 'send flow should use the streaming endpoint');
  assert.match(source, /new AbortController\(\)/, 'streaming must be cancellable');
  assert.match(source, /stop-copilot/, 'a stop control must be wired');
  assert.doesNotMatch(source, /Could not reach Copilot/, 'transport errors must not be persisted as assistant turns');

  const thread = readFileSync(resolve(import.meta.dirname, '../views/copilot/thread.js'), 'utf8');
  assert.match(thread, /renderStreaming/, 'thread should render streaming state');
  assert.match(thread, /data-action="stop-copilot"/, 'streaming turn exposes a Stop button');
});
