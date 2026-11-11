// ---- settings groups: all folded at start, a mouse click on the title opens or closes one (arrow up = open, arrow down = folded) ----
(() => {
  for (const group of document.querySelectorAll('#tab-settings section.group')) {
    const head = group.querySelector(':scope > h3');
    if (!head) continue;
    const body = document.createElement('div');
    body.className = 'fold-body';
    while (head.nextSibling) body.append(head.nextSibling);
    group.append(body);
    head.classList.add('fold-head');
    group.classList.add('folded');
    head.addEventListener('click', () => group.classList.toggle('folded'));
  }
})();
