(() => {
  'use strict';
  const body = document.body;
  const mode = document.getElementById('mode');
  const toggle = document.getElementById('menu-toggle');
  const menu = document.querySelector('.menu');
  const wrapper = document.querySelector('.wrapper');
  const links = document.getElementById('navigation-links');
  const mobile = window.matchMedia('(max-width: 768px)');
  if (!mode || !toggle || !menu || !wrapper || !links) return;

  function syncTheme() {
    const dark = body.dataset.theme === 'dark';
    mode.setAttribute('aria-label', dark ? 'Switch to light theme' : 'Switch to dark theme');
    mode.setAttribute('aria-pressed', String(dark));
  }
  syncTheme();
  body.classList.remove('notransition');
  mode.addEventListener('click', () => {
    const dark = body.dataset.theme !== 'dark';
    if (dark) body.dataset.theme = 'dark';
    else delete body.dataset.theme;
    try { localStorage.setItem('theme', dark ? 'dark' : 'light'); } catch { /* Theme still works without storage. */ }
    syncTheme();
  });
  window.addEventListener('storage', event => {
    if (event.key !== 'theme') return;
    if (event.newValue === 'dark') body.dataset.theme = 'dark';
    else delete body.dataset.theme;
    syncTheme();
  });

  let opened = false;
  function setMenu(open, focus = true) {
    opened = open && mobile.matches;
    menu.classList.toggle('open', opened);
    body.classList.toggle('menu-open', opened);
    wrapper.classList.toggle('blurry', opened);
    wrapper.inert = opened;
    toggle.setAttribute('aria-expanded', String(opened));
    toggle.setAttribute('aria-label', opened ? 'Close navigation' : 'Open navigation');
    if (focus) {
      if (opened) links.querySelector('a')?.focus();
      else toggle.focus();
    }
  }
  toggle.addEventListener('click', () => setMenu(!opened));
  links.addEventListener('click', event => {
    if (event.target.closest('a')) setMenu(false, false);
  });
  mobile.addEventListener('change', () => setMenu(false, false));
  window.addEventListener('pageshow', () => setMenu(false, false));
  document.addEventListener('keydown', event => {
    if (!opened) return;
    if (event.key === 'Escape') { event.preventDefault(); setMenu(false); }
    if (event.key === 'Tab') {
      const controls = [toggle, mode, ...links.querySelectorAll('a')];
      const index = controls.indexOf(document.activeElement);
      event.preventDefault();
      controls[(index + (event.shiftKey ? -1 : 1) + controls.length) % controls.length].focus();
    }
  });

  const email = document.querySelector('.copy-email');
  const status = document.getElementById('copy-status');
  let reset;
  email?.addEventListener('click', async () => {
    clearTimeout(reset);
    try {
      await navigator.clipboard.writeText(email.dataset.email);
      email.setAttribute('aria-label', 'Email copied');
      if (status) status.textContent = 'Email address copied.';
      reset = setTimeout(() => {
        email.setAttribute('aria-label', 'Copy email address');
        if (status) status.textContent = '';
      }, 1500);
    } catch {
      email.setAttribute('aria-label', 'Could not copy email address');
      if (status) status.textContent = `Could not copy. Email: ${email.dataset.email}`;
    }
  });
})();
