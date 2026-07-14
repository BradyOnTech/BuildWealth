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

function installBaseRoutes(page, handleChatStream, {
  conversations = [],
  conversationById = {},
  onDecision = null,
  onboardingStatus = {
    ready_for_daily_review: true,
    completion_percent: 100,
    profile_readiness: { status: 'ready' },
    steps: [],
  },
} = {}) {
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
      const includeArchived = url.searchParams.get('include_archived') === 'true';
      await route.fulfill(jsonResponse(
        conversations.filter(conversation => includeArchived || !conversation.archived_at),
      ));
      return;
    }
    if (/^\/api\/copilot\/conversations\/[^/]+$/.test(url.pathname) && request.method() === 'PATCH') {
      const id = decodeURIComponent(url.pathname.split('/').pop());
      const existing = conversationById[id];
      if (!existing) {
        await route.fulfill(jsonResponse({}, 404));
        return;
      }
      const patch = request.postDataJSON();
      if (typeof patch.title === 'string') existing.title = patch.title;
      if (typeof patch.archived === 'boolean') {
        existing.archived_at = patch.archived ? '2026-07-14T15:00:00.000Z' : null;
      }
      existing.updated_at = '2026-07-14T15:00:00.000Z';
      const summary = conversations.find(conversation => conversation.id === id);
      if (summary) Object.assign(summary, {
        title: existing.title,
        updated_at: existing.updated_at,
        archived_at: existing.archived_at,
      });
      await route.fulfill(jsonResponse(existing));
      return;
    }
    if (/^\/api\/copilot\/conversations\/[^/]+$/.test(url.pathname) && request.method() === 'GET') {
      const id = decodeURIComponent(url.pathname.split('/').pop());
      await route.fulfill(jsonResponse(conversationById[id] || {}, conversationById[id] ? 200 : 404));
      return;
    }
    if (url.pathname === '/api/onboarding/status') {
      await route.fulfill(jsonResponse(onboardingStatus));
      return;
    }
    if (url.pathname === '/api/copilot/chat/stream' && request.method() === 'POST') {
      await handleChatStream(route, request);
      return;
    }
    if (/^\/api\/plans\/[^/]+\/decisions$/.test(url.pathname) && request.method() === 'POST') {
      if (onDecision) onDecision(request.postDataJSON());
      await route.fulfill(jsonResponse({ id: 'plan-1', decisions: [request.postDataJSON()] }));
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
          tool_calls: [{ name: 'get_financial_profile', arguments: {}, result: { reviewed: true } }],
          model: 'fake-model',
          created_at: '2026-07-12T12:00:00.000Z',
          context_trace: { retrieval: { returned_count: 1, citation_count: 0 } },
        },
      },
    ]));
  });

  await page.goto('http://buildwealth-v2.test/#copilot');
  await page.getByPlaceholder(/Message Copilot/).fill('Stream me an answer');
  await page.getByRole('button', { name: /^Send$/ }).click();

  await page.getByText('Here is the streamed answer.').waitFor({ state: 'visible' });
  await page.getByText(/Reviewing your financial profile/).waitFor({ state: 'visible' });
  await page.getByText('Sources & calculations').waitFor({ state: 'visible' });
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
  const sidebarBox = await page.locator('.sidebar').boundingBox();
  const appMainBox = await page.locator('.app-main').boundingBox();
  assert.ok(
    sidebarBox && appMainBox && sidebarBox.y + sidebarBox.height <= appMainBox.y + 1,
    'mobile app navigation should not overlap the Copilot workspace',
  );
  await page.getByText('How can I help?').waitFor();
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

test('Copilot desktop empty state keeps its headline and starter cards inside the scroll viewport', async ({ page }) => {
  await page.setViewportSize({ width: 1536, height: 844 });
  await installBaseRoutes(page, async route => route.fulfill(sseResponse([])), {
    onboardingStatus: {
      ready_for_daily_review: false,
      completion_percent: 0,
      profile_readiness: {
        status: 'incomplete',
        next_gap_title: 'Income profile',
        next_gap_detail: 'Add what comes in each month — salary, business, anything recurring.',
        blocking_recommendation_sources: ['profile_completeness', 'tax_planning'],
        sections: [{ key: 'household', status: 'incomplete' }],
      },
      steps: [{ id: 'income', title: 'Income profile', status: 'incomplete' }],
    },
  });

  await page.goto('http://buildwealth-v2.test/#copilot');
  await page.getByText('How can I help?').waitFor();

  const scrollBox = await page.locator('.copilot-scroll').boundingBox();
  const headlineBox = await page.locator('.copilot-empty-headline').boundingBox();
  const lastStarterBox = await page.locator('.suggestion-card:last-child').boundingBox();
  assert.ok(scrollBox && headlineBox && lastStarterBox);
  assert.ok(
    headlineBox.y >= scrollBox.y,
    'empty-state headline should not be clipped above the scroll viewport',
  );
  assert.ok(
    lastStarterBox.y + lastStarterBox.height <= scrollBox.y + scrollBox.height + 1,
    'starter cards should not be clipped behind the composer',
  );
});

test('Copilot history is searchable, grouped, renameable, and archivable with undo', async ({ page }) => {
  const today = {
    id: 'conv-today',
    title: 'Contribution review',
    created_at: '2026-07-14T12:00:00.000Z',
    updated_at: '2026-07-14T13:00:00.000Z',
    archived_at: null,
    last_message_preview: 'Review the monthly contribution.',
    message_count: 2,
    last_turn_status: 'completed',
  };
  const older = {
    id: 'conv-older',
    title: 'House purchase tradeoff',
    created_at: '2026-06-01T12:00:00.000Z',
    updated_at: '2026-06-01T13:00:00.000Z',
    archived_at: null,
    last_message_preview: 'Compare buying now with waiting.',
    message_count: 2,
    last_turn_status: 'completed',
  };
  const conversationById = Object.fromEntries([today, older].map(conversation => [
    conversation.id,
    { ...conversation, focus: {}, llm: {}, turns: [], messages: [] },
  ]));
  await installBaseRoutes(page, async route => route.fulfill(sseResponse([])), {
    conversations: [today, older],
    conversationById,
  });

  await page.goto('http://buildwealth-v2.test/#copilot');
  await page.getByRole('heading', { name: 'Today' }).waitFor();
  await page.getByRole('heading', { name: 'Older' }).waitFor();

  const search = page.getByRole('searchbox', { name: 'Search chat history' });
  await search.fill('house');
  await page.getByText('House purchase tradeoff').waitFor();
  assert.equal(await page.getByText('Contribution review').count(), 0);
  await search.fill('');

  await page.getByRole('button', { name: 'Chat actions for House purchase tradeoff' }).click();
  await page.getByRole('menuitem', { name: 'Rename' }).click();
  const renameInput = page.getByRole('textbox', { name: 'Rename chat' });
  await renameInput.fill('Home purchase timing');
  await page.getByRole('button', { name: 'Save' }).click();
  await page.getByText('Home purchase timing').waitFor();

  await page.getByRole('button', { name: 'Chat actions for Home purchase timing' }).click();
  await page.getByRole('menuitem', { name: 'Archive' }).click();
  await page.getByText('Archived “Home purchase timing”.').waitFor();
  assert.equal(await page.locator('#copilot-history').getByText('Home purchase timing').count(), 0);
  await page.getByRole('button', { name: 'Undo' }).click();
  await page.locator('#copilot-history').getByText('Home purchase timing').waitFor();

  await page.getByRole('button', { name: 'Chat actions for Home purchase timing' }).click();
  await page.getByRole('menuitem', { name: 'Archive' }).click();
  await page.getByRole('button', { name: 'Show archived chats' }).click();
  await page.getByRole('heading', { name: 'Archived' }).waitFor();
  await page.locator('#copilot-history').getByText('Home purchase timing').waitFor();
  await page.getByRole('button', { name: 'Chat actions for Home purchase timing' }).click();
  await page.getByRole('menuitem', { name: 'Unarchive' }).click();
  await page.getByRole('heading', { name: 'Today' }).waitFor();

  await page.locator('.composer-context').getByText('Primary Plan').waitFor();
  await page.locator('.composer-context-live').click();
  await page.locator('.composer-context').getByText('Live data').waitFor();
});

test('Copilot can track an assistant response as a proposed Plan decision', async ({ page }) => {
  let decisionPayload = null;
  const conversation = {
    id: 'conv-decision',
    title: 'Contribution decision',
    created_at: '2026-07-14T12:00:00.000Z',
    updated_at: '2026-07-14T13:00:00.000Z',
    archived_at: null,
    last_message_preview: 'Increase the contribution after confirming cash reserves.',
    message_count: 2,
    last_turn_status: 'completed',
  };
  await installBaseRoutes(page, async route => route.fulfill(sseResponse([])), {
    conversations: [conversation],
    conversationById: {
      'conv-decision': {
        ...conversation,
        focus: {},
        llm: {},
        turns: [{ id: 'turn-1', status: 'completed' }],
        messages: [{
          id: 'assistant-decision',
          turn_id: 'turn-1',
          role: 'assistant',
          content: 'Increase the contribution after confirming cash reserves.',
          created_at: '2026-07-14T13:00:00.000Z',
          metadata: {},
        }],
      },
    },
    onDecision: payload => { decisionPayload = payload; },
  });

  await page.goto('http://buildwealth-v2.test/#copilot');
  await page.getByText('Contribution decision').click();
  await page.getByRole('button', { name: 'Track decision' }).click();
  await page.getByRole('button', { name: 'Tracked in Plan' }).waitFor();

  assert.equal(decisionPayload.status, 'proposed');
  assert.equal(decisionPayload.action_payload.source, 'copilot_conversation');
  assert.equal(decisionPayload.action_payload.message_id, 'assistant-decision');
  assert.match(decisionPayload.rationale, /Increase the contribution/);
});
