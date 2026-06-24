if ('scrollRestoration' in history) {
  history.scrollRestoration = 'manual';
}

function getScrollOffset() {
  const value = Number.parseFloat(getComputedStyle(document.documentElement).scrollPaddingTop);
  return Number.isFinite(value) ? value : 0;
}

function navigationKind() {
  const nav = performance.getEntriesByType('navigation')[0];
  return nav?.type || 'navigate';
}

function scrollToTopInstant() {
  window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
}

function settleInitialScroll() {
  const isReload = navigationKind() === 'reload';

  if (isReload && window.location.hash) {
    history.replaceState(null, '', `${window.location.pathname}${window.location.search}`);
  }

  if (!isReload && window.location.hash) {
    const target = document.querySelector(window.location.hash);
    if (target) {
      const top = Math.max(0, window.scrollY + target.getBoundingClientRect().top - getScrollOffset());
      window.scrollTo({ top, left: 0, behavior: 'instant' });
      return;
    }
  }

  scrollToTopInstant();
}

const topbar = document.getElementById('topbar');
const readProgress = document.getElementById('readProgress');
const backTop = document.getElementById('backTop');
const tocToggle = document.getElementById('tocToggle');
const tocDrawer = document.getElementById('tocDrawer');
const tocClose = document.getElementById('tocClose');
const tocOverlay = document.getElementById('tocOverlay');
const focusToggle = document.getElementById('focusToggle');
const sectionChip = document.getElementById('sectionChip');
const imageViewer = document.getElementById('imageViewer');
const imageViewerImg = document.getElementById('imageViewerImg');
const imageViewerClose = document.getElementById('imageViewerClose');

const layerSections = [...document.querySelectorAll('[data-layer-section]')];
const layerTabs = [...document.querySelectorAll('.layer-tab')];
const tocGroups = [...document.querySelectorAll('.toc-group')];
const tocChildren = [...document.querySelectorAll('.toc-child')];
const chapters = [...document.querySelectorAll('.chapter-panel')];
let currentChapterId = chapters[0]?.id || '';
let scrollTrackingEnabled = false;

function setProgress() {
  const max = document.documentElement.scrollHeight - window.innerHeight;
  readProgress.style.width = `${max > 0 ? (window.scrollY / max) * 100 : 0}%`;
}

function onScroll() {
  topbar.classList.toggle('is-scrolled', window.scrollY > 6);
  backTop.classList.toggle('is-visible', window.scrollY > 520);
  setProgress();
}

function openToc() {
  tocDrawer.classList.add('is-open');
  tocOverlay.classList.add('is-open');
  document.body.classList.add('toc-open');
}

function closeToc() {
  tocDrawer.classList.remove('is-open');
  tocOverlay.classList.remove('is-open');
  document.body.classList.remove('toc-open');
}

function activeLayer(id) {
  layerTabs.forEach((tab) => tab.classList.toggle('is-active', tab.dataset.layer === id));
  tocGroups.forEach((group) => group.classList.toggle('is-active', group.dataset.layerLink === id));
}

function activeTocLink(id) {
  currentChapterId = id;
  tocChildren.forEach((link) => link.classList.toggle('is-active', link.getAttribute('href') === `#${id}`));
  const target = document.getElementById(id);
  const label = target?.querySelector('.chapter-header h3')?.textContent || target?.querySelector('h2')?.textContent;
  if (label && sectionChip) sectionChip.querySelector('strong').textContent = label;
}

function setFocusMode(enabled) {
  document.body.classList.toggle('focus-mode', enabled);
  focusToggle?.setAttribute('aria-pressed', String(enabled));
  if (focusToggle) focusToggle.textContent = enabled ? '退出专注' : '专注';
}

function findViewportLayerId() {
  const offset = getScrollOffset();
  let best = layerSections[0]?.dataset.layerSection || 'layer-1';
  let bestDistance = Number.POSITIVE_INFINITY;
  layerSections.forEach((section) => {
    const distance = Math.abs(section.getBoundingClientRect().top - offset);
    if (distance < bestDistance) {
      bestDistance = distance;
      best = section.dataset.layerSection;
    }
  });
  return best;
}

function findViewportChapterId() {
  const offset = getScrollOffset();
  let best = chapters[0]?.id || '';
  let bestDistance = Number.POSITIVE_INFINITY;
  chapters.forEach((chapter) => {
    const distance = Math.abs(chapter.getBoundingClientRect().top - offset);
    if (distance < bestDistance) {
      bestDistance = distance;
      best = chapter.id;
    }
  });
  return best;
}

function syncScrollState() {
  activeLayer(findViewportLayerId());
  const chapterId = findViewportChapterId();
  if (chapterId) activeTocLink(chapterId);
}

const layerObserver = new IntersectionObserver((entries) => {
  if (!scrollTrackingEnabled) return;
  const visible = entries
    .filter((entry) => entry.isIntersecting)
    .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
  if (visible) activeLayer(visible.target.dataset.layerSection);
}, { rootMargin: '-24% 0px -64% 0px', threshold: [0.01, 0.1, 0.25] });

layerSections.forEach((section) => layerObserver.observe(section));

const chapterObserver = new IntersectionObserver((entries) => {
  if (!scrollTrackingEnabled) return;
  const visible = entries
    .filter((entry) => entry.isIntersecting)
    .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
  if (visible) activeTocLink(visible.target.id);
}, { rootMargin: '-20% 0px -70% 0px', threshold: [0.01, 0.1] });

chapters.forEach((chapter) => chapterObserver.observe(chapter));

function filterTable(input) {
  const query = input.value.trim().toLowerCase();
  const table = input.closest('.doc-table')?.querySelector('table');
  if (!table) return;
  table.querySelectorAll('tbody tr').forEach((row) => {
    row.classList.toggle('is-filtered-out', query && !row.textContent.toLowerCase().includes(query));
  });
}

function initFontScale() {
  const stored = Number.parseFloat(localStorage.getItem('planningFontScale') || '1');
  if (Number.isFinite(stored)) {
    document.documentElement.style.setProperty('--font-scale', stored);
  }
}

function openImage(src) {
  imageViewerImg.src = src;
  imageViewer.classList.add('is-open');
  imageViewer.setAttribute('aria-hidden', 'false');
  document.body.classList.add('viewer-open');
}

function closeImage() {
  imageViewer.classList.remove('is-open');
  imageViewer.setAttribute('aria-hidden', 'true');
  document.body.classList.remove('viewer-open');
  imageViewerImg.src = '';
}

function openFeatureListTables() {
  document.querySelectorAll('.topic-heading, .subtopic-heading').forEach((heading) => {
    if (!heading.textContent.includes('功能清单')) return;
    let node = heading.nextElementSibling;
    while (node) {
      if (node.matches('.topic-heading, .subtopic-heading')) {
        if (!node.textContent.includes('功能清单')) break;
      } else if (node.matches('.chapter-panel, .chapter-header')) {
        break;
      } else if (node.matches('.doc-table')) {
        node.open = true;
      }
      node = node.nextElementSibling;
    }
  });
}

function fitLayerTitles() {
  document.querySelectorAll('.layer-header h2').forEach((title) => {
    title.style.removeProperty('font-size');
    let size = Number.parseFloat(getComputedStyle(title).fontSize);
    if (!Number.isFinite(size)) size = 18;

    title.style.fontSize = `${size}px`;
    while (size > 11 && title.scrollWidth > title.clientWidth + 1) {
      size -= 0.5;
      title.style.fontSize = `${size}px`;
    }
  });
}

let layerTitleFitTimer;

function scheduleLayerTitleFit() {
  clearTimeout(layerTitleFitTimer);
  layerTitleFitTimer = window.setTimeout(() => {
    requestAnimationFrame(fitLayerTitles);
  }, 60);
}

function watchLayerTitleFit() {
  if (typeof ResizeObserver === 'undefined') return;
  const observer = new ResizeObserver(scheduleLayerTitleFit);
  document.querySelectorAll('.layer-header').forEach((header) => observer.observe(header));
}

function enhancePageLayout() {
  document.querySelectorAll('.layer-section').forEach((layer) => {
    const layerChapters = [...layer.querySelectorAll('.chapter-panel')];
    layerChapters.forEach((chapter, index) => {
      chapter.dataset.chapterIndex = String(index + 1);
      if (chapter.querySelector('.doc-table')) chapter.classList.add('chapter-panel--spec');
      if (chapter.querySelector('.doc-figure')) chapter.classList.add('chapter-panel--visual');
      if (index % 2 === 1) chapter.classList.add('chapter-panel--alt');
    });
  });

  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  const revealObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('is-revealed');
        revealObserver.unobserve(entry.target);
      }
    });
  }, { threshold: 0.08 });

  document.querySelectorAll('.quick-card').forEach((node) => {
    node.classList.add('reveal-block');
    revealObserver.observe(node);
  });
}

function bootstrapScrollState() {
  settleInitialScroll();
  scrollTrackingEnabled = true;
  syncScrollState();
  onScroll();
}

window.addEventListener('scroll', onScroll, { passive: true });
window.addEventListener('resize', () => {
  setProgress();
  scheduleLayerTitleFit();
}, { passive: true });
window.addEventListener('pageshow', (event) => {
  if (!event.persisted) return;
  openFeatureListTables();
  bootstrapScrollState();
  scheduleLayerTitleFit();
});

tocToggle?.addEventListener('click', openToc);
tocClose?.addEventListener('click', closeToc);
tocOverlay?.addEventListener('click', closeToc);
backTop?.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));

document.addEventListener('click', (event) => {
  const anchor = event.target.closest('a[href^="#"]');
  if (anchor && document.querySelector(anchor.getAttribute('href'))) closeToc();

  const imageButton = event.target.closest('[data-full-image]');
  if (imageButton) openImage(imageButton.dataset.fullImage);
});

document.querySelectorAll('.table-filter').forEach((input) => {
  input.addEventListener('input', () => filterTable(input));
});

focusToggle?.addEventListener('click', () => {
  const keepId = findViewportChapterId() || currentChapterId;
  setFocusMode(!document.body.classList.contains('focus-mode'));
  requestAnimationFrame(() => {
    const target = keepId ? document.getElementById(keepId) : null;
    if (!target) return;
    const top = Math.max(0, window.scrollY + target.getBoundingClientRect().top - getScrollOffset());
    window.scrollTo(0, top);
    scheduleLayerTitleFit();
  });
});
imageViewerClose?.addEventListener('click', closeImage);
imageViewer?.addEventListener('click', (event) => {
  if (event.target === imageViewer) closeImage();
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    closeToc();
    closeImage();
  }
});

initFontScale();
setFocusMode(false);
openFeatureListTables();
enhancePageLayout();
watchLayerTitleFit();
scheduleLayerTitleFit();
bootstrapScrollState();
requestAnimationFrame(bootstrapScrollState);
document.fonts?.ready?.then(scheduleLayerTitleFit);
window.addEventListener('load', () => {
  bootstrapScrollState();
  scheduleLayerTitleFit();
}, { once: true });
