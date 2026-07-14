import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { dirname, extname, isAbsolute, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { test } from '@playwright/test';

const currentDir = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(currentDir, '..');

const CONTENT_TYPES = {
  '.css': 'text/css',
  '.html': 'text/html',
  '.js': 'text/javascript',
};

const jsonResponse = (body, status = 200) => ({
  status,
  contentType: 'application/json',
  body: JSON.stringify(body),
});

const sseResponse = events => ({
  status: 200,
  contentType: 'text/event-stream',
  body: events.map(event => `data: ${JSON.stringify(event)}\n\n`).join(''),
});

async function staticResponse(pathname) {
  const relativePath = pathname === '/' ? 'index.html' : pathname.replace(/^\/static-v2\//, '');
  const filePath = resolve(webRoot, relativePath);
  const distance = relative(webRoot, filePath);
  assert.ok(
    distance && !distance.startsWith('..') && !isAbsolute(distance),
    `refusing to serve path outside web root: ${pathname}`,
  );
  return {
    status: 200,
    contentType: CONTENT_TYPES[extname(filePath)] || 'text/plain',
    body: await readFile(filePath, 'utf8'),
  };
}

function installBaseRoutes(page, handleChatStream, { conversations = [], conversationById = {} } = {}) {
  return page.route('**/*', async route => {
    const request = route.request();
    const url = new URL(request.url());

    if (url.hostname !== 'buildwealth-v2.test') {
      await route.abort();
      return;
    }
    if (url.pathname === '/' || url.pathname.startsWith('/static-v2/')) {
      await route.fulfill(await staticResponse(url.pathname));
      return;
    }
    if (url.pathname === '/api/plans') {
      await route.fulfill(jsonResponse([{ id: 'plan-1', title: 'Primary Plan', is_active: true }]));
      return;
    }
    if (url.pathname === '/api/copilot/conversations') {
      await route.fulfill(jsonResponse(conversations));
      return;
    }
    if (url.pathname.startsWith('/api/copilot/conversations/') && request.method() === 'GET') {
      const id = decodeURIComponent(url.pathname.split('/').pop());
      await route.fulfill(jsonResponse(conversationById[id] || {}, conversationById[id] ? 200 : 404));
      return;
    }
    if (url.pathname === '/api/onboarding/status') {
      await route.fulfill(jsonResponse({
        ready_for_daily_review: true,
        completion_percent: 100,
        profile_readiness: { status: 'ready' },
        steps: [],
      }));
      return;
    }
    if (url.pathname === '/api/copilot/chat/stream' && request.method() === 'POST') {
      await handleChatStream(route, request);
      return;
    }
    await route.fulfill(jsonResponse({}));
  });
}

test('Copilot consumes the SSE stream and renders the final answer', async ({ page }) => {
  let streamPayload = null;
  await installBaseRoutes(page, async (route, request) => {
    streamPayload = request.postDataJSON();
    await route.fulfill(sseResponse([
      { type: 'stage', stage: 'assembling_context' },
      { type: 'round', round: 1 },
      { type: 'tool', name: 'get_financial_profile', status: 'start' },
      { type: 'tool', name: 'get_financial_profile', status: 'done' },
      { type: 'answer_delta', text: 'Here is the ' },
      { type: 'answer_delta', text: 'streamed answer.' },
      {
        type: 'result',
        data: {
          conversation_id: 'conv-stream',
          answer: 'Here is the streamed answer.',
          tool_calls: [],
          model: 'fake-model',
          created_at: '2026-07-12T12:00:00.000Z',
          context_trace: {},
        },
      },
    ]));
  });

  await page.goto('http://buildwealth-v2.test/#copilot');
  await page.getByPlaceholder(/Message Copilot/).fill('Stream me an answer');
  await page.getByRole('button', { name: /^Send$/ }).click();

  await page.getByText('Here is the streamed answer.').waitFor({ state: 'visible' });
  assert.equal(streamPayload.question, 'Stream me an answer');
});

test('Copilot stream errors surface as a banner, not an assistant message', async ({ page }) => {
  await installBaseRoutes(page, async route => {
    await route.fulfill(sseResponse([
      { type: 'stage', stage: 'assembling_context' },
      { type: 'error', status: 502, detail: 'LLM provider error: upstream unavailable' },
    ]));
  });

  await page.goto('http://buildwealth-v2.test/#copilot');
  await page.getByPlaceholder(/Message Copilot/).fill('This one fails');
  await page.getByRole('button', { name: /^Send$/ }).click();

  await page.locator('.error-banner').getByText(/upstream unavailable/).waitFor({ state: 'visible' });
  // The failed turn must not be persisted as an assistant reply.
  assert.equal(await page.locator('.message.assistant').count(), 0);
});

test('Copilot history reopens old chats and preserves drafts per conversation', async ({ page }) => {
  const oldChat = {
    id: 'conv-old',
    title: 'Retirement contribution review',
    created_at: '2026-07-10T12:00:00.000Z',
    updated_at: '2026-07-12T12:00:00.000Z',
    last_message_preview: 'Increasing the contribution improves plan strength.',
    message_count: 2,
    last_turn_status: 'completed',
  };
  await installBaseRoutes(page, async route => {
    await route.fulfill(sseResponse([]));
  }, {
    conversations: [oldChat],
    conversationById: {
      'conv-old': {
        ...oldChat,
        focus: {},
        llm: {},
        turns: [{
          id: 'turn-old',
          status: 'completed',
          user_message_id: 'user-old',
          assistant_message_id: 'assistant-old',
        }],
        messages: [
          {
            id: 'user-old',
            turn_id: 'turn-old',
            role: 'user',
            content: 'Should I increase my retirement contribution?',
            created_at: '2026-07-10T12:00:00.000Z',
            metadata: {},
          },
          {
            id: 'assistant-old',
            turn_id: 'turn-old',
            role: 'assistant',
            content: 'Increasing the contribution improves plan strength.',
            created_at: '2026-07-10T12:01:00.000Z',
            metadata: {},
          },
        ],
      },
    },
  });

  await page.goto('http://buildwealth-v2.test/#copilot');
  const composer = page.getByPlaceholder(/Message Copilot/);
  await composer.fill('Unsent new-chat question');

  await page.locator('.copilot-history-item', { hasText: 'Retirement contribution review' }).click();
  await page.getByText('Increasing the contribution improves plan strength.').waitFor();
  await composer.fill('Unsent follow-up for the old chat');

  await page.locator('.copilot-history-new').click();
  assert.equal(await composer.inputValue(), 'Unsent new-chat question');

  await page.locator('.copilot-history-item', { hasText: 'Retirement contribution review' }).click();
  await page.getByText('Increasing the contribution improves plan strength.').waitFor();
  assert.equal(await composer.inputValue(), 'Unsent follow-up for the old chat');
});

test('Copilot history opens as a usable drawer on mobile', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const conversation = {
    id: 'conv-mobile',
    title: 'Mobile history chat',
    created_at: '2026-07-10T12:00:00.000Z',
    updated_at: '2026-07-12T12:00:00.000Z',
    last_message_preview: '',
    message_count: 0,
    last_turn_status: '',
  };
  await installBaseRoutes(page, async route => route.fulfill(sseResponse([])), {
    conversations: [conversation],
    conversationById: {
      'conv-mobile': { ...conversation, focus: {}, llm: {}, turns: [], messages: [] },
    },
  });

  await page.goto('http://buildwealth-v2.test/#copilot');
  await page.getByRole('button', { name: 'Open chat history' }).click();

  const history = page.locator('#copilot-history');
  await history.getByText('Mobile history chat').waitFor();
  await page.waitForFunction(() => {
    const element = document.querySelector('#copilot-history');
    return element && element.getBoundingClientRect().x >= 0;
  });
  const box = await history.boundingBox();
  assert.ok(box && box.x >= 0 && box.x < 30, 'history drawer should be inside the viewport');

  await history.getByText('Mobile history chat').click();
  await page.getByRole('button', { name: 'Open chat history' }).waitFor();
  await page.waitForFunction(() => {
    const element = document.querySelector('#copilot-history');
    return element && element.getBoundingClientRect().right <= 25;
  });
});
