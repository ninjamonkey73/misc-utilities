chrome.action.onClicked.addListener((tab) => {
  chrome.scripting.executeScript({
    target: { tabId: tab.id },
    files: ['content.js']
  });
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.html) {
    const title = message.title || 'Extracted Paragraphs';
    const fullHtml = '<!DOCTYPE html><html><head><meta charset="UTF-8"><title>' + title + '</title><style>body{max-width:800px;margin:40px auto;padding:0 20px;font-family:Georgia,serif;line-height:1.6;color:#333}h1{margin-bottom:1em;border-bottom:1px solid #ccc;padding-bottom:0.5em}p{margin-bottom:1em}a{color:#0066cc}</style></head><body><h1>' + title + '</h1>' + message.html + '</body></html>';

    const dataUrl = 'data:text/html;charset=utf-8,' + encodeURIComponent(fullHtml);
    chrome.tabs.create({ url: dataUrl });
  }
});
