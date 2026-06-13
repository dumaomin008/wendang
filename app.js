/* ===== Navigation Tree ===== */
const NAV_TREE = [
  {
    id: '1', label: '第一层：战略层', subtitle: '定义平台的边界与灵魂', href: '#layer-intro',
    children: [
      { label: '总述', href: '#layer-intro' },
      { label: '背景趋势', href: '#background' },
      { label: '商业论证', href: '#business-case' },
      { label: '角色痛点', href: '#roles' },
      { label: '平台定位', href: '#positioning' },
      { label: '竞争壁垒', href: '#moat' },
      { label: '平台边界', href: '#boundaries' },
    ],
  },
  {
    id: '2', label: '第二层：用户层', subtitle: '全景用户画像与全链路场景地图', href: '#layer2-intro',
    children: [
      { label: '总述', href: '#layer2-intro' },
      { label: '端产品矩阵', href: '#layer2-matrix' },
      { label: '阶段一 · 获客', href: '#layer2-phase1' },
      { label: '阶段二 · 转化', href: '#layer2-phase2' },
      { label: '阶段三 · 资产', href: '#layer2-phase3' },
      { label: '阶段四 · 运营', href: '#layer2-phase4' },
      { label: '阶段五 · 后市场', href: '#layer2-phase5' },
    ],
  },
  {
    id: '3', label: '第三层：全平台功能与架构全景蓝图', href: '#layer3-intro',
    children: [
      { label: '总述', href: '#layer3-intro' },
      { label: '架构全景图', href: '#layer3-blueprint' },
      { label: '3.1 触点交互层', href: '#layer3-31' },
      { label: '3.2 核心业务链', href: '#layer3-32' },
      { label: '3.3 基础支撑', href: '#layer3-33' },
      { label: '3.4 数据中台', href: '#layer3-34' },
      { label: '3.5 AI 赋能', href: '#layer3-35' },
      { label: '3.6 金融生态', href: '#layer3-36' },
    ],
  },
  {
    id: '4', label: '第四层：子系统功能与架构', href: '#layer4-intro',
    children: [
      { label: '总述', href: '#layer4-intro' },
      { label: '市场转化中心', href: '#layer4-market' },
      { label: '资产价值中心', href: '#layer4-asset' },
      { label: '物流智运中心', href: '#layer4-tms' },
      { label: '安全后市场', href: '#layer4-safety' },
      { label: '补能能源中心', href: '#layer4-energy' },
    ],
  },
  {
    id: '5', label: '第五层：产品路线规划', href: '#layer5-intro',
    children: [
      { label: '总述', href: '#layer5-intro' },
      { label: '短期 · 运营闭环', href: '#layer5-short' },
      { label: '中期 · 数据深化', href: '#layer5-mid' },
      { label: '长期 · 生态金融', href: '#layer5-long' },
    ],
  },
];

const STAGGER_MS = 40;
const MAX_STAGGER = 6;

const nav = document.getElementById('nav');
const sidebar = document.getElementById('sidebar');
const docNav = document.getElementById('docNav');
const sidebarOverlay = document.getElementById('sidebarOverlay');
const navMenuBtn = document.getElementById('navMenuBtn');
const sidebarClose = document.getElementById('sidebarClose');
const readProgress = document.getElementById('readProgress');
const backTop = document.getElementById('backTop');
const navLayerTabs = document.querySelectorAll('.nav-layer-tab');
const navLogo = document.getElementById('navLogo');

let scrollTimer = null;
let reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/* ===== In-page navigation ===== */
function getScrollOffset() {
  const padding = parseFloat(getComputedStyle(document.documentElement).scrollPaddingTop);
  return Number.isFinite(padding) ? padding : 0;
}

function findLayerForHref(href) {
  return NAV_TREE.find((g) => g.children.some((c) => c.href === href));
}

function jumpTo(href) {
  const target = document.querySelector(href);
  if (!target) return false;
  const top = Math.max(0, window.scrollY + target.getBoundingClientRect().top - getScrollOffset());
  window.scrollTo(0, top);
  history.replaceState(null, '', href);
  return true;
}

function markDocNav(href) {
  const layer = findLayerForHref(href);
  docNav.querySelectorAll('.doc-nav-group').forEach((group) => {
    group.classList.toggle('is-current', group.dataset.layer === layer?.id);
  });
  docNav.querySelectorAll('.doc-nav-link').forEach((link) => {
    link.classList.toggle('is-active', link.getAttribute('href') === href);
  });
}

function syncTopTabs(href) {
  const layer = findLayerForHref(href);
  navLayerTabs.forEach((tab) => {
    tab.classList.toggle('active', tab.dataset.layer === layer?.id);
  });
}

function navigate(href, { closeDrawer = true } = {}) {
  if (!href || !href.startsWith('#')) return;
  if (!jumpTo(href)) return;
  markDocNav(href);
  syncTopTabs(href);
  if (closeDrawer) closeSidebar();
}

function initDocNav() {
  docNav.innerHTML = NAV_TREE.map((group) => `
    <section class="doc-nav-group${group.id === '1' ? ' is-current' : ''}" data-layer="${group.id}">
      <button type="button" class="doc-nav-layer" data-href="${group.href}">
        <span class="doc-nav-layer-title">${group.label}</span>
        ${group.subtitle ? `<span class="doc-nav-layer-desc">${group.subtitle}</span>` : ''}
      </button>
      <ul class="doc-nav-items">
        ${group.children.map((item) => `
          <li><a href="${item.href}" class="doc-nav-link">${item.label}</a></li>
        `).join('')}
      </ul>
    </section>
  `).join('');
}

function initGlobalAnchors() {
  document.addEventListener('click', (e) => {
    const anchor = e.target.closest('a[href^="#"]');
    if (!anchor) return;
    const href = anchor.getAttribute('href');
    if (!href || href === '#') return;
    if (!document.querySelector(href)) return;
    e.preventDefault();
    const closeDrawer = Boolean(anchor.closest('.sidebar, .doc-nav, .nav-layers'));
    navigate(href, { closeDrawer });
  });
}

function openSidebar() {
  sidebar.classList.add('open');
  sidebarOverlay.classList.add('visible');
  document.body.classList.add('sidebar-open');
}

function closeSidebar() {
  sidebar.classList.remove('open');
  sidebarOverlay.classList.remove('visible');
  document.body.classList.remove('sidebar-open');
}

navMenuBtn?.addEventListener('click', openSidebar);
sidebarClose?.addEventListener('click', closeSidebar);
sidebarOverlay?.addEventListener('click', closeSidebar);

navLogo?.addEventListener('click', (e) => {
  e.preventDefault();
  navigate('#layer-intro', { closeDrawer: false });
});

/* ===== Scroll Spy ===== */
const spyIds = [];
NAV_TREE.forEach((g) => g.children.forEach((c) => spyIds.push(c.href.slice(1))));
const spyElements = spyIds.map((id) => document.getElementById(id)).filter(Boolean);

function updateActiveNav() {
  const marker = window.scrollY + window.innerHeight * 0.26;
  let currentId = spyElements[0]?.id || '';

  for (const el of spyElements) {
    const top = el.getBoundingClientRect().top + window.scrollY;
    if (top <= marker) currentId = el.id;
  }

  const href = `#${currentId}`;
  markDocNav(href);
  syncTopTabs(href);
}

function onScroll() {
  nav.classList.toggle('scrolled', window.scrollY > 8);

  const docHeight = document.documentElement.scrollHeight - window.innerHeight;
  readProgress.style.width = `${docHeight > 0 ? (window.scrollY / docHeight) * 100 : 0}%`;

  readProgress.classList.add('is-scrolling');
  clearTimeout(scrollTimer);
  scrollTimer = setTimeout(() => readProgress.classList.remove('is-scrolling'), 400);

  backTop.classList.toggle('visible', window.scrollY > 480);
  updateActiveNav();
}

backTop?.addEventListener('click', () => {
  window.scrollTo(0, 0);
});

/* ===== Module Collapse (L4) ===== */
function wrapModuleBodies() {
  document.querySelectorAll('.module-block').forEach((block) => {
    const h3 = block.querySelector(':scope > h3');
    if (!h3 || block.querySelector(':scope > .module-block-body')) return;

    const body = document.createElement('div');
    body.className = 'module-block-body';
    const nodes = [...block.childNodes].filter(
      (n) => n !== h3 && (n.nodeType !== 3 || n.textContent.trim())
    );
    nodes.forEach((n) => body.appendChild(n));
    block.appendChild(body);
  });
}

function initModuleCollapse() {
  wrapModuleBodies();

  document.querySelectorAll('.module-block > h3').forEach((h3) => {
    h3.classList.add('module-toggle');
    h3.setAttribute('role', 'button');
    h3.setAttribute('tabindex', '0');
    h3.setAttribute('aria-expanded', 'true');

    const toggle = () => toggleModule(h3.closest('.module-block'));
    h3.addEventListener('click', toggle);
    h3.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        toggle();
      }
    });
  });
}

function toggleModule(block) {
  if (!block) return;
  const collapsed = block.classList.toggle('collapsed');
  block.querySelector('.module-toggle')?.setAttribute('aria-expanded', String(!collapsed));
}

document.getElementById('expandAll')?.addEventListener('click', () => {
  document.querySelectorAll('.module-block.collapsed').forEach((b) => toggleModule(b));
});

document.getElementById('collapseAll')?.addEventListener('click', () => {
  document.querySelectorAll('.module-block:not(.collapsed)').forEach((b) => toggleModule(b));
});

/* ===== Reveal (section-level only) ===== */
const REVEAL_SELECTORS = [
  '.section-header',
  '.intro-card',
  '.layer-nav-grid',
  '.layer-divider',
  '.subsys-position',
  '.subsys-diagram',
  '.blueprint-card',
  '.arch-diagram',
  '.layer5-phase-timeline',
  '.roadmap-table-wrap',
  '.scenario-table-wrap',
];

function initReveal() {
  const targets = document.querySelectorAll(REVEAL_SELECTORS.join(','));
  targets.forEach((el) => el.classList.add('reveal'));

  if (reducedMotion) {
    targets.forEach((el) => el.classList.add('visible'));
    return;
  }

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('visible');
        observer.unobserve(entry.target);
      });
    },
    { threshold: 0.08, rootMargin: '0px 0px -5% 0px' }
  );

  targets.forEach((el) => observer.observe(el));
}

function initFromHash() {
  const hash = window.location.hash;
  if (!hash || !document.querySelector(hash)) return;
  jumpTo(hash);
  markDocNav(hash);
  syncTopTabs(hash);
}

document.querySelectorAll('.roadmap-table-wrap, .scenario-table-wrap').forEach((wrap) => {
  if (wrap.scrollWidth > wrap.clientWidth) wrap.classList.add('has-scroll');
});

/* ===== Init ===== */
initDocNav();
initGlobalAnchors();
initModuleCollapse();
initReveal();
initFromHash();

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeSidebar();
});

window.addEventListener('hashchange', initFromHash);
window.addEventListener('scroll', onScroll, { passive: true });
onScroll();

document.body.classList.add('motion-ready');
