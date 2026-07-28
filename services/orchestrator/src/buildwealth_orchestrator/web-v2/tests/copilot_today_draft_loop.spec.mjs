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

const sseResponse = event => ({
  status: 200,
  contentType: 'text/event-stream',
  body: `data: ${JSON.stringify(event)}\n\n`,
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

test('Copilot drafted investment review surfaces in Today and opens focused Inbox row', async ({ page }) => {
  let draftCreated = false;
  const chatPayloads = [];

  const draftedRecommendation = () => ({
    id: 'rec-copilot-invest',
    title: 'Review NVDA fit before changing exposure',
    detail: 'NVDA conflicts with current concentration policy. Review fit context before making any portfolio decision.',
    priority: 'high',
    status: 'proposed',
    source: 'copilot:investment_fit',
    recommendation_type: 'workflow_action',
    created_at: '2026-04-26T12:00:00Z',
    updated_at: '2026-04-26T12:00:00Z',
    action_payload: {
      generator: {
        id: 'copilot_investment_fit_draft',
        signal_type: 'investment_fit_discussion',
      },
      evidence: {
        symbol: 'NVDA',
        provider: 'yfinance',
        freshness_status: 'fresh',
        confidence: 'high',
        fit_status: 'does_not_fit',
        fit_score: 25,
        fit_risks: ['NVDA would worsen concentration risk.'],
        research_evidence_packet_id: 'research-evidence:yfinance:NVDA:6mo:1d',
      },
      suggested_action: {
        kind: 'review_portfolio_fit',
        symbol: 'NVDA',
        fit_status: 'does_not_fit',
      },
      quality: {
        actionability: 'review_only',
        confidence_level: 'high',
        freshness_status: 'fresh',
        reversibility: 'high',
        impact: { level: 'high' },
        blocking_context: [],
        decision_grade: true,
      },
    },
    score: {
      total: 92,
      rank: 1,
      reasons: ['Copilot drafted this review from investment-fit context.'],
    },
  });

  await page.route('**/*', async route => {
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

    if (url.pathname === '/api/copilot/conversations') {
      await route.fulfill(jsonResponse([]));
      return;
    }

    if (
      ['/api/copilot/chat', '/api/copilot/chat/stream'].includes(url.pathname)
      && request.method() === 'POST'
    ) {
      const payload = request.postDataJSON();
      chatPayloads.push(payload);
      assert.match(payload.question || '', /NVDA/i);
      draftCreated = true;
      const result = {
        conversation_id: 'conversation-investment-fit',
        answer: 'I drafted a review-only investment recommendation for your Inbox.',
        created_at: '2026-04-26T12:00:00.000Z',
        model: 'browser-test',
        tool_calls: [
          {
            name: 'draft_investment_research_recommendation',
            arguments: { symbol: 'NVDA' },
            result: {
              draft_kind: 'investment_research_recommendation',
              requires_review: true,
              recommendation: draftedRecommendation(),
            },
          },
        ],
      };
      await route.fulfill(
        url.pathname.endsWith('/stream')
          ? sseResponse({ type: 'result', data: result })
          : jsonResponse(result),
      );
      return;
    }

    if (url.pathname === '/api/dashboard/today') {
      await route.fulfill(jsonResponse({
        generated_at: '2026-04-26T12:00:00Z',
        currency: 'USD',
        state: 'MN',
        sync_status: { running: false, runs_total: 1, runs_failed: 0 },
        net_worth_usd: 300000,
        monthly_surplus_usd: 2500,
        savings_rate_pct: 25,
        context_state: 'warning',
        context_notes: [],
        command_cards: draftCreated ? [
          {
            id: 'copilot-drafts',
            title: 'Copilot prepared reviews',
            status: 'warning',
            detail: '1 Copilot-drafted review is waiting: NVDA · fresh evidence · review-only.',
            metric_label: 'Drafts',
            metric_value: '1',
            action_label: 'Review draft',
            href: '#inbox?focus=rec-copilot-invest',
          },
        ] : [],
        top_next_actions: [],
      }));
      return;
    }

    if (url.pathname === '/api/services/status') {
      await route.fulfill(jsonResponse({
        enabled_count: 2,
        reachable_count: 2,
        degraded_count: 0,
        services: [],
      }));
      return;
    }

    if (url.pathname === '/api/recommendations') {
      const requestedStatus = url.searchParams.get('status') || 'proposed';
      await route.fulfill(jsonResponse(
        draftCreated && requestedStatus === 'proposed' ? [draftedRecommendation()] : [],
      ));
      return;
    }

    if (url.pathname === '/api/recommendations/closure-analytics') {
      await route.fulfill(jsonResponse({}));
      return;
    }

    if (url.pathname === '/api/plans') {
      await route.fulfill(jsonResponse([]));
      return;
    }

    if (url.pathname === '/api/onboarding/status') {
      await route.fulfill(jsonResponse({
        ready_for_daily_review: true,
        completion_percent: 100,
        profile_readiness: { status: 'ready', completion_percent: 100 },
        steps: [],
      }));
      return;
    }

    await route.fulfill(jsonResponse({ detail: `Unhandled test route: ${request.method()} ${url.pathname}` }, 404));
  });

  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('http://buildwealth-v2.test/#copilot');
  await page.locator('#composer[data-composer-ready="true"]').waitFor();
  await page.locator('#composer-textarea').fill('Draft a review-only recommendation for NVDA from this investment-fit discussion.');
  await page.locator('#composer-submit').click();

  await page.getByText('Drafted investment review').waitFor({ state: 'visible' });
  await page.getByText('Review NVDA fit before changing exposure').waitFor({ state: 'visible' });
  await page.getByRole('link', { name: /Open in Inbox/ }).waitFor({ state: 'visible' });
  assert.equal(chatPayloads.length, 1);
  assert.equal(draftCreated, true);

  await page.goto('http://buildwealth-v2.test/#today');
  await page.getByText('Copilot prepared reviews').waitFor({ state: 'visible' });
  await page.getByText('NVDA · fresh evidence · review-only').waitFor({ state: 'visible' });

  await page.getByRole('link', { name: 'Review draft' }).click();
  await page.waitForURL('**/#inbox?focus=rec-copilot-invest');
  await page.getByText('Review NVDA fit before changing exposure').waitFor({ state: 'visible' });
  await page.getByText('Investment-fit route').waitFor({ state: 'visible' });
  await page.getByText('symbol NVDA · fresh evidence · via yfinance · does not fit fit').waitFor({ state: 'visible' });
});
