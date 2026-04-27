(() => {
  // Try h1 first, fall back to document title
  const h1 = document.querySelector('h1');
  const title = h1 ? h1.innerText : document.title;

  const paragraphs = document.querySelectorAll('p');
  const html = Array.from(paragraphs)
    .map(p => `<p>${p.innerHTML}</p>`)
    .join('\n');

  chrome.runtime.sendMessage({ title, html });
})();
