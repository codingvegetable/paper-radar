const state = {
  papers: [],
  activeCategory: 'all',
  query: '',
};

const categoryOrder = ['all', 'manipulation', 'vla', 'uav', 'humanoid'];
const categoryNames = {
  all: 'All',
  manipulation: 'Manipulation',
  vla: 'VLA',
  uav: 'UAV',
  humanoid: 'Humanoid',
};

const elements = {
  updatedAt: document.querySelector('#updatedAt'),
  tabs: document.querySelector('#categoryTabs'),
  stats: document.querySelector('#stats'),
  grid: document.querySelector('#paperGrid'),
  empty: document.querySelector('#emptyState'),
  emptyTitle: document.querySelector('#emptyTitle'),
  emptyText: document.querySelector('#emptyText'),
  search: document.querySelector('#searchInput'),
  template: document.querySelector('#paperCardTemplate'),
};

async function loadPapers() {
  try {
    const response = await fetch('data/papers.json', { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    state.papers = payload.papers ?? [];
    elements.updatedAt.textContent = formatDateTime(payload.updated_at) || '等待首次更新';
  } catch (error) {
    console.error(error);
    elements.updatedAt.textContent = '数据加载失败';
    state.papers = [];
  }

  renderTabs();
  renderStats();
  renderPapers();
}

function formatDateTime(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

function formatDate(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 10);
  return new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric' }).format(date);
}

function countByCategory() {
  const counts = Object.fromEntries(categoryOrder.map((key) => [key, 0]));
  counts.all = state.papers.length;
  for (const paper of state.papers) {
    for (const key of paper.category_keys ?? []) {
      counts[key] = (counts[key] ?? 0) + 1;
    }
  }
  return counts;
}

function renderTabs() {
  const counts = countByCategory();
  elements.tabs.replaceChildren(...categoryOrder.map((key) => {
    const button = document.createElement('button');
    button.className = key === state.activeCategory ? 'tab active' : 'tab';
    button.type = 'button';
    button.dataset.category = key;
    button.textContent = `${categoryNames[key]} ${counts[key] ?? 0}`;
    button.addEventListener('click', () => {
      state.activeCategory = key;
      renderTabs();
      renderPapers();
    });
    return button;
  }));
}

function renderStats() {
  const latest = state.papers[0]?.published ? formatDate(state.papers[0].published) : 'N/A';
  const cards = [
    ['Total Papers', state.papers.length],
    ['Latest Paper', latest],
    ['Source', 'arXiv'],
  ];
  elements.stats.replaceChildren(...cards.map(([label, value]) => {
    const card = document.createElement('article');
    card.className = 'stat-card';
    const strong = document.createElement('strong');
    strong.textContent = value;
    const span = document.createElement('span');
    span.textContent = label;
    card.append(strong, span);
    return card;
  }));
}

function getFilteredPapers() {
  const query = state.query.trim().toLowerCase();
  return state.papers.filter((paper) => {
    const matchesCategory = state.activeCategory === 'all' || (paper.category_keys ?? []).includes(state.activeCategory);
    const haystack = [
      paper.title,
      paper.abstract,
      ...(paper.keywords ?? []),
      ...(paper.authors ?? []),
    ].join(' ').toLowerCase();
    return matchesCategory && (!query || haystack.includes(query));
  });
}

function renderPapers() {
  const papers = getFilteredPapers();
  elements.grid.replaceChildren(...papers.map(createPaperCard));
  elements.empty.hidden = papers.length > 0;
  if (!state.papers.length) {
    elements.emptyTitle.textContent = '等待首次论文数据';
    elements.emptyText.textContent = '部署后运行一次 GitHub Action，或本地执行 scripts/fetch_papers.py 生成 data/papers.json。';
  } else {
    elements.emptyTitle.textContent = '没有匹配的论文';
    elements.emptyText.textContent = '换一个关键词或分类试试。';
  }
}

function createPaperCard(paper) {
  const fragment = elements.template.content.cloneNode(true);
  const card = fragment.querySelector('.paper-card');
  card.style.setProperty('--accent', paper.category_color || '#2f6f6d');
  fragment.querySelector('.category').textContent = paper.categories?.[0] ?? 'Paper';
  fragment.querySelector('.date').textContent = formatDate(paper.published);
  fragment.querySelector('.title').textContent = paper.title;
  fragment.querySelector('.summary').textContent = paper.abstract;

  const keywords = fragment.querySelector('.keywords');
  keywords.replaceChildren(...(paper.keywords ?? []).map((keyword) => {
    const badge = document.createElement('span');
    badge.textContent = keyword;
    return badge;
  }));

  const links = fragment.querySelector('.links');
  const abstractLink = createLink('arXiv', paper.links?.abstract);
  const pdfLink = createLink('PDF', paper.links?.pdf);
  const authorNote = document.createElement('small');
  authorNote.textContent = formatAuthors(paper.authors);
  links.append(abstractLink, pdfLink, authorNote);
  return fragment;
}

function createLink(label, href) {
  const link = document.createElement('a');
  link.textContent = label;
  if (href) {
    link.href = href;
    link.target = '_blank';
    link.rel = 'noreferrer';
  } else {
    link.setAttribute('aria-disabled', 'true');
  }
  return link;
}

function formatAuthors(authors = []) {
  if (!authors.length) return 'Authors unavailable';
  if (authors.length <= 3) return authors.join(', ');
  return `${authors.slice(0, 3).join(', ')} +${authors.length - 3}`;
}

elements.search.addEventListener('input', (event) => {
  state.query = event.target.value;
  renderPapers();
});

loadPapers();
