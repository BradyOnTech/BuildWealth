import test from 'node:test';
import assert from 'node:assert/strict';
import { authScreen } from '../views/auth.js';

test('authScreen: renders sign-in form by default', () => {
  const markup = String(authScreen());
  assert.match(markup, /Welcome back to BuildWealth/);
  assert.match(markup, /name="email"/);
  assert.match(markup, /name="password"/);
  assert.match(markup, /data-auth-mode="login"/);
  assert.doesNotMatch(markup, /name="display_name"/);
});

test('authScreen: renders registration form with household workspace language', () => {
  const markup = String(authScreen({ mode: 'register' }));
  assert.match(markup, /Create your BuildWealth account/);
  assert.match(markup, /name="display_name"/);
  assert.match(markup, /Demo data will stay separate/);
  assert.match(markup, /data-auth-mode="register"/);
});

test('authScreen: surfaces auth errors accessibly', () => {
  const markup = String(authScreen({ error: 'Invalid email or password' }));
  assert.match(markup, /role="alert"/);
  assert.match(markup, /Invalid email or password/);
});
