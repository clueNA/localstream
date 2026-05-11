const baseUrl = window.location.origin;
const params = new URLSearchParams(window.location.search);
const mediaId = params.get('id');

const player = document.getElementById('player');
const titleEl = document.getElementById('title');
const detailsEl = document.getElementById('details');
const descriptionEl = document.getElementById('description');
const subtitleInfoEl = document.getElementById('subtitle-info');
const speedSelect = document.getElementById('speed-select');
const themeToggle = document.getElementById('theme-toggle');
const favoriteBtn = document.getElementById('favorite-btn');

const modal = document.getElementById('password-modal');
const passwordInput = document.getElementById('password-input');
const passwordSubmit = document.getElementById('password-submit');

const favoritesKey = 'favorites';
const progressKey = 'watchProgress';
const tokenKey = 'streamToken';

let streamPasswordRequired = false;

function applyTheme() {
  const theme = localStorage.getItem('theme') || 'dark';
  document.body.classList.toggle('light', theme === 'light');
}

function toggleTheme() {
  const theme = localStorage.getItem('theme') || 'dark';
  localStorage.setItem('theme', theme === 'dark' ? 'light' : 'dark');
  applyTheme();
}

function getFavorites() {
  return new Set(JSON.parse(localStorage.getItem(favoritesKey) || '[]'));
}

function saveFavorites(favorites) {
  localStorage.setItem(favoritesKey, JSON.stringify([...favorites]));
}

function getToken() {
  return sessionStorage.getItem(tokenKey) || '';
}

async function requestToken(password) {
  const response = await fetch(`${baseUrl}/api/auth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  });
  if (!response.ok) {
    throw new Error('Invalid password');
  }
  const data = await response.json();
  sessionStorage.setItem(tokenKey, data.token);
}

function ensurePassword() {
  if (!streamPasswordRequired) return;
  if (getToken()) return;
  modal.classList.remove('hidden');
  passwordSubmit.onclick = async () => {
    if (passwordInput.value.trim()) {
      try {
        await requestToken(passwordInput.value.trim());
        modal.classList.add('hidden');
        loadMedia();
      } catch (error) {
        alert('Invalid password');
      }
    }
  };
}

function updateFavoriteButton(isFavorite) {
  favoriteBtn.textContent = isFavorite ? '★ Favorited' : '☆ Favorite';
}

function loadProgress() {
  const progress = JSON.parse(localStorage.getItem(progressKey) || '{}');
  return progress[mediaId];
}

function saveProgress(current, duration) {
  const progress = JSON.parse(localStorage.getItem(progressKey) || '{}');
  if (duration && current < duration) {
    progress[mediaId] = {
      current,
      duration,
      percent: (current / duration) * 100,
    };
  } else {
    delete progress[mediaId];
  }
  localStorage.setItem(progressKey, JSON.stringify(progress));
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

function buildStreamUrl(media) {
  const token = getToken();
  const url = new URL(media.stream_url || `${baseUrl}/api/stream/${mediaId}`);
  if (token) {
    url.searchParams.set('token', token);
  }
  const canPlay = player.canPlayType(media.mime_type || '');
  if (!canPlay) {
    url.searchParams.set('transcode', '1');
  }
  return url.toString();
}

async function loadMedia() {
  if (!mediaId) {
    window.location.href = '/';
    return;
  }

  const response = await fetch(`${baseUrl}/api/media/${mediaId}`);
  const media = await response.json();

  titleEl.textContent = media.title;
  const duration = media.duration ? `${Math.round(media.duration / 60)} min` : 'Unknown length';
  detailsEl.textContent = `${duration} • ${media.width || '-'}x${media.height || '-'} • ${media.video_codec || ''}`;
  descriptionEl.textContent = media.description || '';

  const favorites = getFavorites();
  updateFavoriteButton(favorites.has(media.id));
  favoriteBtn.onclick = () => {
    const next = getFavorites();
    if (next.has(media.id)) {
      next.delete(media.id);
    } else {
      next.add(media.id);
    }
    saveFavorites(next);
    updateFavoriteButton(next.has(media.id));
  };

  const streamUrl = buildStreamUrl(media);
  player.src = streamUrl;

  if (media.subtitle_tracks && media.subtitle_tracks.length) {
    subtitleInfoEl.textContent = 'Subtitles available';
    media.subtitle_tracks.forEach((track, index) => {
      const trackEl = document.createElement('track');
      trackEl.kind = 'subtitles';
      trackEl.label = track.label || track.language || `Track ${index + 1}`;
      trackEl.srclang = track.language || 'en';
      const trackUrl = new URL(`${baseUrl}/api/media/${media.id}/subtitles/${track.id}`);
      const token = getToken();
      if (token) {
        trackUrl.searchParams.set('token', token);
      }
      trackEl.src = trackUrl.toString();
      player.appendChild(trackEl);
    });
  } else {
    subtitleInfoEl.textContent = 'No subtitles detected';
  }

  const stored = loadProgress();
  if (stored && stored.current) {
    player.currentTime = stored.current;
  }

  let lastSaved = 0;
  player.addEventListener('timeupdate', () => {
    if (Math.abs(player.currentTime - lastSaved) >= 5) {
      saveProgress(player.currentTime, player.duration);
      lastSaved = player.currentTime;
    }
  });

  player.addEventListener('ended', () => {
    saveProgress(player.duration, player.duration);
  });
}

speedSelect.addEventListener('change', (event) => {
  player.playbackRate = Number(event.target.value);
});

themeToggle.addEventListener('click', toggleTheme);

applyTheme();
loadInfo().then(() => {
  if (!streamPasswordRequired || getToken()) {
    loadMedia();
  }
});
