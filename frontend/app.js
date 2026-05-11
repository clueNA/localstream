const baseUrl = window.location.origin;
const searchInput = document.getElementById('search');
const themeToggle = document.getElementById('theme-toggle');
const modal = document.getElementById('password-modal');
const passwordInput = document.getElementById('password-input');
const passwordSubmit = document.getElementById('password-submit');

const continueGrid = document.getElementById('continue-grid');
const recentGrid = document.getElementById('recent-grid');
const allGrid = document.getElementById('all-grid');

let mediaItems = [];
let streamPasswordRequired = false;

const favoritesKey = 'favorites';
const progressKey = 'watchProgress';

function getFavorites() {
  return new Set(JSON.parse(localStorage.getItem(favoritesKey) || '[]'));
}

function saveFavorites(favorites) {
  localStorage.setItem(favoritesKey, JSON.stringify([...favorites]));
}

function getProgress() {
  return JSON.parse(localStorage.getItem(progressKey) || '{}');
}

function applyTheme() {
  const theme = localStorage.getItem('theme') || 'dark';
  document.body.classList.toggle('light', theme === 'light');
}

function toggleTheme() {
  const theme = localStorage.getItem('theme') || 'dark';
  localStorage.setItem('theme', theme === 'dark' ? 'light' : 'dark');
  applyTheme();
}

function ensurePassword() {
  if (!streamPasswordRequired) return;
  const stored = localStorage.getItem('streamPassword');
  if (stored) return;
  modal.classList.remove('hidden');
  passwordSubmit.onclick = () => {
    if (passwordInput.value.trim()) {
      localStorage.setItem('streamPassword', passwordInput.value.trim());
      modal.classList.add('hidden');
    }
  };
}

function cardTemplate(media, progress) {
  const card = document.createElement('div');
  card.className = 'media-card';
  card.onclick = () => {
    window.location.href = `/watch?id=${media.id}`;
  };

  const img = document.createElement('img');
  img.src = media.poster_url || 'https://via.placeholder.com/300x450?text=LocalStream';
  img.alt = media.title;

  const info = document.createElement('div');
  info.className = 'info';
  const title = document.createElement('div');
  title.className = 'title';
  title.textContent = media.title;
  const meta = document.createElement('div');
  meta.className = 'meta';
  const duration = media.duration ? `${Math.round(media.duration / 60)} min` : 'Unknown';
  meta.textContent = `${duration}${progress ? ` • ${Math.round(progress.percent)}% watched` : ''}`;

  info.append(title, meta);
  card.append(img, info);

  const favorites = getFavorites();
  if (favorites.has(media.id)) {
    const badge = document.createElement('div');
    badge.className = 'favorite';
    badge.textContent = '★';
    card.appendChild(badge);
  }

  return card;
}

function render() {
  const query = searchInput.value.toLowerCase();
  const progress = getProgress();
  const filtered = mediaItems.filter((item) => item.title.toLowerCase().includes(query));

  const recent = filtered.slice(0, 8);
  const continueItems = filtered
    .filter((item) => progress[item.id])
    .map((item) => ({ item, progress: progress[item.id] }));

  continueGrid.innerHTML = '';
  if (continueItems.length === 0) {
    document.getElementById('continue-section').style.display = 'none';
  } else {
    document.getElementById('continue-section').style.display = 'block';
    continueItems.forEach(({ item }) => {
      continueGrid.appendChild(cardTemplate(item, progress[item.id]));
    });
  }

  recentGrid.innerHTML = '';
  recent.forEach((item) => recentGrid.appendChild(cardTemplate(item, progress[item.id])));

  allGrid.innerHTML = '';
  filtered.forEach((item) => allGrid.appendChild(cardTemplate(item, progress[item.id])));
}

async function loadMedia() {
  const response = await fetch(`${baseUrl}/api/media`);
  mediaItems = await response.json();
  render();
}

async function loadInfo() {
  try {
    const response = await fetch(`${baseUrl}/api/info`);
    const info = await response.json();
    streamPasswordRequired = info.stream_password_required;
  } catch (error) {
    console.warn('Failed to load info', error);
  }
  ensurePassword();
}

searchInput.addEventListener('input', render);
themeToggle.addEventListener('click', toggleTheme);

applyTheme();
loadInfo();
loadMedia();
