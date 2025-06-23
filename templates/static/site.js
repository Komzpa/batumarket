function loadList(name) {
  try { return JSON.parse(localStorage.getItem(name) || '[]'); } catch (e) { return []; }
}

function saveList(name, arr) {
  localStorage.setItem(name, JSON.stringify(arr));
}

function parseJSON(str) {
  try { return JSON.parse(str); } catch (e) { return null; }
}

function cosSim(a, b) {
  let dot = 0, na = 0, nb = 0;
  for (let i = 0; i < a.length && i < b.length; i++) {
    dot += a[i] * b[i];
    na += a[i] * a[i];
    nb += b[i] * b[i];
  }
  if (na === 0 || nb === 0) return 0;
  return dot / Math.sqrt(na * nb);
}

function bestSim(vec, arr) {
  let best = 0;
  for (const item of arr) {
    if (!item.vec) continue;
    const s = cosSim(vec, item.vec);
    if (s > best) best = s;
  }
  return best;
}

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-set-lang]').forEach(a => {
    a.addEventListener('click', () => {
      localStorage.setItem('lang', a.dataset.setLang);
    });
  });

  document.querySelectorAll('th[data-sort]').forEach(th => {
    th.addEventListener('click', () => {
      const table = th.closest('table');
      const idx = th.cellIndex;
      const tbody = table.tBodies[0];
      if (!tbody) return;
      const rows = Array.from(tbody.rows);
      const asc = !th.classList.contains('asc');
      const type = th.dataset.sort;
      rows.sort((a, b) => {
        const ac = a.cells[idx];
        const bc = b.cells[idx];
        let A = ac ? (ac.dataset.raw || ac.textContent) : '';
        let B = bc ? (bc.dataset.raw || bc.textContent) : '';
        if (type === 'number') {
          A = parseFloat(A);
          B = parseFloat(B);
          const na = Number.isNaN(A);
          const nb = Number.isNaN(B);
          if (na && !nb) return 1;
          if (!na && nb) return -1;
          if (na && nb) return 0;
        } else if (type === 'time') {
          A = Date.parse(A);
          B = Date.parse(B);
          const na = Number.isNaN(A);
          const nb = Number.isNaN(B);
          if (na && !nb) return 1;
          if (!na && nb) return -1;
          if (na && nb) return 0;
        }
        return (A > B ? 1 : (A < B ? -1 : 0)) * (asc ? 1 : -1);
      });
      const frag = document.createDocumentFragment();
      rows.forEach(r => frag.appendChild(r));
      tbody.innerHTML = '';
      tbody.appendChild(frag);
      table.querySelectorAll('th').forEach(h => h.classList.remove('asc', 'desc'));
      th.classList.add(asc ? 'asc' : 'desc');
    });
  });

  const mainCarousel = document.querySelector('.carousel.main');
  if (mainCarousel) {
    const images = Array.from(mainCarousel.querySelectorAll('img'));
    const lightbox = document.createElement('div');
    lightbox.className = 'lightbox';
    lightbox.innerHTML = '<span class="prev">\u2039</span><img><span class="next">\u203A</span>';
    document.body.appendChild(lightbox);
    const lbImg = lightbox.querySelector('img');
    const prev = lightbox.querySelector('.prev');
    const next = lightbox.querySelector('.next');
    let idx = 0;
    function show(i) {
      idx = (i + images.length) % images.length;
      lbImg.src = images[idx].src;
      lightbox.style.display = 'flex';
    }
    images.forEach((img, i) => {
      img.addEventListener('click', () => show(i));
    });
    lightbox.addEventListener('click', e => {
      if (e.target === lightbox) lightbox.style.display = 'none';
    });
    prev.addEventListener('click', e => { e.stopPropagation(); show(idx - 1); });
    next.addEventListener('click', e => { e.stopPropagation(); show(idx + 1); });
  }

  if (window.currentLot) {
    const likeBtn = document.getElementById('like-btn');
    const dislikeBtn = document.getElementById('dislike-btn');
    function update() {
      const likes = loadList('likes');
      const dislikes = loadList('dislikes');
      const liked = likes.some(i => i.id === window.currentLot.id);
      const dis = dislikes.some(i => i.id === window.currentLot.id);
      likeBtn.classList.toggle('active', liked);
      dislikeBtn.classList.toggle('active', dis);
    }
    likeBtn.addEventListener('click', () => {
      let likes = loadList('likes').filter(i => i.id !== window.currentLot.id);
      likes.push({id: window.currentLot.id, vec: window.currentLot.vector});
      saveList('likes', likes);
      let dislikes = loadList('dislikes').filter(i => i.id !== window.currentLot.id);
      saveList('dislikes', dislikes);
      update();
    });
    dislikeBtn.addEventListener('click', () => {
      let dislikes = loadList('dislikes').filter(i => i.id !== window.currentLot.id);
      dislikes.push({id: window.currentLot.id, vec: window.currentLot.vector});
      saveList('dislikes', dislikes);
      let likes = loadList('likes').filter(i => i.id !== window.currentLot.id);
      saveList('likes', likes);
      update();
    });
    update();
  }

  const sortSelect = document.getElementById('sort-mode');
  const indexTable = document.getElementById('index-table');
  if (sortSelect && indexTable) {
    function relevanceKey(vec) {
      const likes = loadList('likes');
      const dislikes = loadList('dislikes');
      if (!vec || (likes.length === 0 && dislikes.length === 0)) {
        return { sign: 0, dist: Infinity };
      }
      const likeScore = bestSim(vec, likes);
      const dislikeScore = bestSim(vec, dislikes);
      if (likeScore >= dislikeScore && likeScore > 0) {
        return { sign: 1, dist: 1 - likeScore };
      }
      if (dislikeScore > likeScore && dislikeScore > 0) {
        return { sign: -1, dist: 1 - dislikeScore };
      }
      return { sign: 0, dist: Infinity };
    }
    function scoreUnexplored(vec) {
      const base = loadList('likes').concat(loadList('dislikes'));
      if (!vec || base.length === 0) return 0;
      let best = 0;
      for (const item of base) {
        if (!item.vec) continue;
        const s = cosSim(vec, item.vec);
        if (s > best) best = s;
      }
      return -best;
    }
    function applySort() {
      const mode = sortSelect.value;
      localStorage.setItem('sort-mode', mode);
      const tbody = indexTable.tBodies[0];
      if (!tbody) return;
      const rows = Array.from(tbody.rows);
      rows.sort((a, b) => {
        if (mode === 'price_asc' || mode === 'price_desc') {
          const pa = parseFloat(a.dataset.price);
          const pb = parseFloat(b.dataset.price);
          const na = Number.isNaN(pa);
          const nb = Number.isNaN(pb);
          if (na && !nb) return 1;
          if (!na && nb) return -1;
          if (na && nb) return 0;
          return mode === 'price_asc' ? pa - pb : pb - pa;
        }
        const va = parseJSON(a.dataset.vector || 'null');
        const vb = parseJSON(b.dataset.vector || 'null');
        if (mode === 'relevance') {
          const ra = relevanceKey(va);
          const rb = relevanceKey(vb);
          if (ra.sign !== rb.sign) return rb.sign - ra.sign;
          if (ra.dist !== rb.dist) return ra.dist - rb.dist;
          return 0;
        }
        if (mode === 'unexplored') {
          return scoreUnexplored(vb) - scoreUnexplored(va);
        }
        return 0;
      });
      const frag = document.createDocumentFragment();
      rows.forEach(r => frag.appendChild(r));
      tbody.innerHTML = '';
      tbody.appendChild(frag);
    }
    sortSelect.value = localStorage.getItem('sort-mode') || 'relevance';
    sortSelect.addEventListener('change', applySort);
    applySort();
  }
});
