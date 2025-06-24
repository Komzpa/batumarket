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

  // Table header sorting was removed. Use the dropdown instead.

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
      likes.push({id: window.currentLot.id, vec: window.currentLot.embed});
      saveList('likes', likes);
      let dislikes = loadList('dislikes').filter(i => i.id !== window.currentLot.id);
      saveList('dislikes', dislikes);
      update();
    });
    dislikeBtn.addEventListener('click', () => {
      let dislikes = loadList('dislikes').filter(i => i.id !== window.currentLot.id);
      dislikes.push({id: window.currentLot.id, vec: window.currentLot.embed});
      saveList('dislikes', dislikes);
      let likes = loadList('likes').filter(i => i.id !== window.currentLot.id);
      saveList('likes', likes);
      update();
    });
    update();
  }

  const sortSelect  = document.getElementById('sort-mode');
  const indexTable  = document.getElementById('index-table');

  if (!sortSelect || !indexTable) return;

  // data rows have <td> cells, header or spacer rows have <th>
  const isDataRow = row => row.querySelector('td') !== null;

  const price   = row => parseFloat(row.dataset.price);
  const vector  = row => parseJSON(row.dataset.embed || 'null');
  const rawTime = cell =>
      Date.parse(cell.dataset.raw || cell.textContent.trim() || '');

  function relevanceKey(vec) {
    const likes = loadList('likes');
    const dislikes = loadList('dislikes');
    if (!vec || (!likes.length && !dislikes.length))
      return { sign: 0, dist: Infinity };

    const like = bestSim(vec, likes);
    const dislike = bestSim(vec, dislikes);

    if (like >= dislike && like > 0) return { sign: 1, dist: 1 - like };
    if (dislike > like && dislike > 0) return { sign: -1, dist: 1 - dislike };
    return { sign: 0, dist: Infinity };
  }

  function unexploredScore(vec) {
    const base = loadList('likes').concat(loadList('dislikes'));
    if (!vec || !base.length) return 0;
    return -bestSim(vec, base);
  }

  /** helper – returns an array of only real <tr> children */
  function grabRows(body) {
    return Array.from(body.children).filter(el => el.tagName === 'TR');
  }

  function resortTable(mode) {
    const oldBody  = indexTable.tBodies[0];
    const rows     = grabRows(oldBody);
    const staticRows = rows.filter(r => !isDataRow(r));
    const dataRows   = rows.filter(isDataRow);

    dataRows.sort((a, b) => {
      if (mode.startsWith('price')) {
        const pa = price(a), pb = price(b);
        if (Number.isNaN(pa) || Number.isNaN(pb)) return Number.isNaN(pa) - Number.isNaN(pb);
        return mode.endsWith('_asc') ? pa - pb : pb - pa;
      }

      if (mode.startsWith('time')) {
        const ta = rawTime(a.cells[a.cells.length - 1]);
        const tb = rawTime(b.cells[b.cells.length - 1]);
        if (Number.isNaN(ta) || Number.isNaN(tb)) return Number.isNaN(ta) - Number.isNaN(tb);
        return mode.endsWith('_asc') ? ta - tb : tb - ta;
      }

      const va = vector(a), vb = vector(b);

      if (mode === 'relevance') {
        const ra = relevanceKey(va), rb = relevanceKey(vb);
        if (ra.sign !== rb.sign) return rb.sign - ra.sign;
        return ra.dist - rb.dist;
      }

      if (mode === 'unexplored')
        return unexploredScore(vb) - unexploredScore(va);

      return 0;
    });

    const fresh = document.createElement('tbody');
    fresh.append(...staticRows, ...dataRows);

    oldBody.replaceWith(fresh);
  }

  sortSelect.addEventListener('change', () => {
    const mode = sortSelect.value;
    localStorage.setItem('sort-mode', mode);
    resortTable(mode);
  });

  sortSelect.value = localStorage.getItem('sort-mode') || 'relevance';
  resortTable(sortSelect.value);
});
