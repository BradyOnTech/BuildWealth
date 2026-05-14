import { html, raw } from '../lib/dom.js';

export function authScreen({ mode = 'login', error = '', busy = false, authConfig = null } = {}) {
  const isRegister = mode === 'register';
  const hostedEnabled = Boolean(authConfig?.hosted_auth_enabled);
  const localEnabled = authConfig?.local_auth_enabled !== false;
  const hostedProvider = authConfig?.hosted_provider_name || 'your identity provider';
  const hostedLoginUrl = authConfig?.hosted_login_url || '/api/auth/hosted/login';
  return html`
    <main class="auth-shell" data-auth-screen>
      <section class="auth-panel">
        <div class="auth-brand">
          <p class="brand-monogram">B<span class="ampersand">&amp;</span>W</p>
          <p class="brand-eyebrow">The Wealth Almanac</p>
        </div>
        <header class="auth-head">
          <p class="auth-kicker">Private household workspace</p>
          <h1>${isRegister ? 'Create your BuildWealth account' : 'Welcome back to BuildWealth'}</h1>
          <p>
            ${isRegister
              ? 'Set up the owner account for your household workspace. Demo data will stay separate from your real financial picture.'
              : 'Sign in to open your household workspace, recommendations, simulations, and profile data.'}
          </p>
        </header>
        ${hostedEnabled ? html`
          <a class="btn btn-primary auth-submit" href="${hostedLoginUrl}">
            Continue with ${hostedProvider}
          </a>
        ` : ''}
        ${localEnabled ? raw(localAuthForm({ isRegister, busy, error })) : ''}
        ${localEnabled ? raw(localAuthSwitch({ isRegister })) : ''}
        ${!localEnabled && error ? html`<p class="auth-error" role="alert">${error}</p>` : ''}
      </section>
    </main>
  `;
}

function localAuthForm({ isRegister, busy, error }) {
  return html`
    <form class="auth-form" id="auth-form" data-auth-mode="${isRegister ? 'register' : 'login'}">
      ${isRegister ? html`
        <label class="auth-field">
          <span>Name</span>
          <input name="display_name" autocomplete="name" placeholder="Your name" ${busy ? 'disabled' : ''} />
        </label>
      ` : ''}
      <label class="auth-field">
        <span>Email</span>
        <input name="email" type="email" autocomplete="email" required placeholder="you@example.com" ${busy ? 'disabled' : ''} />
      </label>
      <label class="auth-field">
        <span>Password</span>
        <input name="password" type="password" autocomplete="${isRegister ? 'new-password' : 'current-password'}" required minlength="8" ${busy ? 'disabled' : ''} />
      </label>
      ${error ? html`<p class="auth-error" role="alert">${error}</p>` : ''}
      <button class="btn btn-primary auth-submit" type="submit" ${busy ? 'disabled' : ''}>
        ${busy ? 'Working...' : (isRegister ? 'Create account' : 'Sign in')}
      </button>
    </form>
  `;
}

function localAuthSwitch({ isRegister }) {
  return html`
    <footer class="auth-switch">
      ${isRegister ? html`
        <span>Already have an account?</span>
        <button type="button" data-auth-mode-switch="login">Sign in</button>
      ` : html`
        <span>Setting up this BuildWealth workspace?</span>
        <button type="button" data-auth-mode-switch="register">Create account</button>
      `}
    </footer>
  `;
}
