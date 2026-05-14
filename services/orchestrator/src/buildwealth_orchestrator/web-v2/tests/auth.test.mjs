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

test('authScreen: renders hosted identity without local password fields when configured', () => {
  const markup = String(authScreen({
    authConfig: {
      hosted_auth_enabled: true,
      local_auth_enabled: false,
      hosted_provider_name: 'Test OIDC',
      hosted_login_url: '/api/auth/hosted/login',
    },
  }));

  assert.match(markup, /Continue with Test OIDC/);
  assert.match(markup, /href="\/api\/auth\/hosted\/login"/);
  assert.doesNotMatch(markup, /name="password"/);
  assert.doesNotMatch(markup, /data-auth-mode="login"/);
});

test('authScreen: surfaces hosted callback errors without local fields', () => {
  const markup = String(authScreen({
    error: 'Hosted sign-in could not be completed',
    authConfig: {
      hosted_auth_enabled: true,
      local_auth_enabled: false,
      hosted_provider_name: 'Test OIDC',
      hosted_login_url: '/api/auth/hosted/login',
    },
  }));

  assert.match(markup, /Continue with Test OIDC/);
  assert.match(markup, /role="alert"/);
  assert.match(markup, /Hosted sign-in could not be completed/);
  assert.doesNotMatch(markup, /name="password"/);
});
