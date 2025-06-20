function switchLang(lang) {
  document.querySelectorAll('.lang').forEach(el => {
    el.classList.toggle('active', el.dataset.lang === lang);
  });
  localStorage.setItem('lang', lang);
}

document.addEventListener('DOMContentLoaded', () => {
  const saved = localStorage.getItem('lang');
  if (saved) switchLang(saved);
  document.querySelectorAll('[data-set-lang]').forEach(btn => {
    btn.addEventListener('click', () => switchLang(btn.dataset.setLang));
  });
});
