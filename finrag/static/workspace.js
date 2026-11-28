const menu = document.querySelector('.nav-toggle');
menu.addEventListener('click', () => {
  const open = document.body.classList.toggle('nav-open');
  menu.setAttribute('aria-expanded', String(open));
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && document.body.classList.contains('nav-open')) menu.click();
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault();
    const search = document.getElementById('search');
    if (search) search.focus();
    else window.location.assign('/library#search');
  }
});

const searchBox = document.getElementById('search');
if (searchBox) {
  if (location.hash === '#search') searchBox.focus();
  searchBox.addEventListener('input', () => {
    const terms = searchBox.value.toLowerCase().trim().split(/\s+/);
    const rows = Array.from(document.querySelectorAll('[data-search]'));
    for (const row of rows) row.hidden = !terms.every(t => row.dataset.search.toLowerCase().includes(t));
    document.getElementById('no-match').hidden = !rows.length || rows.some(row => !row.hidden);
  });
}

const form = document.getElementById('ask-form');
if (form) {
  const question = form.elements.question;
  const options = document.getElementById('query-options');
  const toggle = form.querySelector('.option-toggle');
  options.hidden = true;
  toggle.addEventListener('click', () => {
    options.hidden = !options.hidden;
    toggle.setAttribute('aria-expanded', String(!options.hidden));
  });
  for (const pick of document.querySelectorAll('[data-prompt]')) {
    pick.addEventListener('click', () => {
      question.value = pick.dataset.prompt;
      form.elements.doc.value = pick.dataset.doc;
      question.focus();
    });
  }
  question.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter' && !event.isComposing) form.requestSubmit();
  });
  const send = document.getElementById('send');
  const busy = document.getElementById('ask-progress');
  form.addEventListener('submit', event => {
    if (send.disabled) { event.preventDefault(); return; }
    send.disabled = true;
    busy.hidden = false;
  });
  window.addEventListener('pageshow', () => { send.disabled = false; busy.hidden = true; });
}
