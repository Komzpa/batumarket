document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-set-lang]').forEach(a => {
    a.addEventListener('click', () => {
      localStorage.setItem('lang', a.dataset.setLang);
    });
  });

  document.querySelectorAll('th[data-sort]').forEach(th => {
    th.addEventListener('click', () => {
      const table = th.closest('table');
      const idx = Array.from(th.parentNode.children).indexOf(th);
      const tbody = table.querySelector('tbody');
      const rows = Array.from(tbody.querySelectorAll('tr'));
      const asc = !th.classList.contains('asc');
      const type = th.dataset.sort;
      rows.sort((a, b) => {
        let A = a.cells[idx].dataset.raw || a.cells[idx].textContent;
        let B = b.cells[idx].dataset.raw || b.cells[idx].textContent;
        if (type === 'number') {
          A = parseFloat(A) || 0;
          B = parseFloat(B) || 0;
        } else if (type === 'time') {
          A = Date.parse(A);
          B = Date.parse(B);
        }
        return (A > B ? 1 : (A < B ? -1 : 0)) * (asc ? 1 : -1);
      });
      tbody.innerHTML = '';
      rows.forEach(r => tbody.appendChild(r));
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
});
