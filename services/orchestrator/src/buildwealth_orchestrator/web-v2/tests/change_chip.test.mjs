import test from 'node:test';
import assert from 'node:assert/strict';
import { changeChip, windowLabel, chipDirection } from '../lib/change_chip.js';

test('windowLabel names the span honestly', () => {
  assert.equal(windowLabel(1), 'past day');
  assert.equal(windowLabel(6), 'past 6 days');
  assert.equal(windowLabel(14), 'past 2 weeks');
  assert.equal(windowLabel(31), 'past month');
  assert.equal(windowLabel(90), 'past 3 months');
  assert.equal(windowLabel(400), 'past year');
  assert.equal(windowLabel(800), 'past 2 years');
  assert.equal(windowLabel(null), '');
});

test('chipDirection treats exact zero as flat', () => {
  assert.equal(chipDirection(15000, 5.2), 'up');
  assert.equal(chipDirection(-4200, -1.4), 'down');
  assert.equal(chipDirection(0, 0), 'flat');
});

test('changeChip renders delta, percent, window, and basis', () => {
  const markup = String(changeChip({
    deltaUsd: 15000,
    deltaPct: 5.2,
    windowDays: 31,
    basis: 'portfolio',
  }));
  assert.match(markup, /change-chip delta-up/);
  assert.match(markup, /↑/);
  assert.match(markup, /\+\$15,000/);
  assert.match(markup, /\(\+5\.2%\)/);
  assert.match(markup, /past month/);
  assert.match(markup, /portfolio/);
});

test('changeChip renders declines with the down treatment', () => {
  const markup = String(changeChip({ deltaUsd: -23292.75, deltaPct: -3.5, windowDays: 30 }));
  assert.match(markup, /change-chip delta-down/);
  assert.match(markup, /↓/);
  assert.match(markup, /-\$23,293/);
  assert.match(markup, /past month/);
});

test('changeChip never fabricates: no delta, no chip', () => {
  assert.equal(String(changeChip({ deltaUsd: null, deltaPct: null, windowDays: 31 })), '');
  assert.equal(String(changeChip({})), '');
});

test('changeChip omits the window when history cannot say how long', () => {
  const markup = String(changeChip({ deltaUsd: 1200, deltaPct: 1.1 }));
  assert.match(markup, /\+\$1,200/);
  assert.doesNotMatch(markup, /past /);
});

test('changeChip escapes a hostile basis label', () => {
  const markup = String(changeChip({ deltaUsd: 5, deltaPct: 0.1, basis: '<img src=x onerror=alert(1)>' }));
  assert.doesNotMatch(markup, /<img/);
  assert.match(markup, /&lt;img/);
});
