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
});
