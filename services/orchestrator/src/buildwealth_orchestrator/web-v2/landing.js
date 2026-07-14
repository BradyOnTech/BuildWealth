/* ─────────────────────────────────────────────────
   Landing · motion + reveals
   Small, dependency-free. Every effect degrades to
   "already visible" when JS or IntersectionObserver
   is missing, or when the user prefers reduced motion.
   ───────────────────────────────────────────────── */

const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/* ── Masthead: gain a hairline + weight once the page scrolls ── */
const masthead = document.querySelector('.lp-masthead');
if (masthead) {
  const onScroll = () => masthead.classList.toggle('is-scrolled', window.scrollY > 8);
  onScroll();
  window.addEventListener('scroll', onScroll, { passive: true });
}

/* ── Scroll reveals: fade/rise sections as they enter view ── */
const revealEls = document.querySelectorAll('[data-reveal], [data-reveal-stagger]');

if (reduceMotion || !('IntersectionObserver' in window)) {
  revealEls.forEach((el) => el.classList.add('in-view'));
} else {
  // Stagger children by assigning transition-delay per index.
  document.querySelectorAll('[data-reveal-stagger]').forEach((group) => {
    const step = Number(group.dataset.revealStagger) || 60;
    [...group.children].forEach((child, i) => {
      child.style.transitionDelay = `${Math.min(i * step, 480)}ms`;
    });
  });

  const io = new IntersectionObserver(
    (entries, obs) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('in-view');
        obs.unobserve(entry.target); // reveal once, then stop watching
      });
    },
    { rootMargin: '0px 0px -12% 0px', threshold: 0.12 },
  );
  revealEls.forEach((el) => io.observe(el));
}

/* ── One-time count-up on the hero net-worth figure ── */
const counter = document.querySelector('[data-count-to]');
if (counter) {
  const target = Number(counter.dataset.countTo);
  const prefix = counter.dataset.countPrefix || '';
  const render = (v) =>
    `${prefix}${Math.round(v).toLocaleString('en-US')}`;

  if (reduceMotion || !('IntersectionObserver' in window)) {
    counter.textContent = render(target);
  } else {
    counter.textContent = render(0);
    const spin = new IntersectionObserver(
      (entries, obs) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          obs.disconnect();
          const dur = 1100;
          const start = performance.now();
          const ease = (t) => 1 - Math.pow(1 - t, 3); // ease-out cubic
          const tick = (now) => {
            const p = Math.min((now - start) / dur, 1);
            counter.textContent = render(target * ease(p));
            if (p < 1) requestAnimationFrame(tick);
          };
          requestAnimationFrame(tick);
        });
      },
      { threshold: 0.5 },
    );
    spin.observe(counter);
  }
}

/* ── Smooth in-page anchor scrolling, honoring reduced motion ── */
document.querySelectorAll('a[href^="#"]').forEach((link) => {
  link.addEventListener('click', (e) => {
    const id = link.getAttribute('href');
    if (!id || id === '#') return;
    const target = document.querySelector(id);
    if (!target) return;
    e.preventDefault();
    target.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
  });
});
