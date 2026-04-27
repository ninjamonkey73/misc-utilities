# Paragraph Extractor

A Chrome extension that extracts all `<p>` tags from a page and opens them in a clean, readable new tab.

## Features

- Extracts article title (from `<h1>` or page title)
- Preserves inner HTML (links, bold, italics, etc.)
- Clean, readable styling in the output

## Installation

1. Open Chrome and navigate to `chrome://extensions`
2. Enable **Developer mode** (toggle in top right)
3. Click **Load unpacked**
4. Select the `paragraph-extractor` folder

## Usage

1. Navigate to any webpage with paragraphs (articles, blog posts, etc.)
2. Click the extension icon (blue "P" square)
3. A new tab opens with just the extracted paragraphs

## Troubleshooting

**Extension icon doesn't appear:**
- Check that the extension is enabled in `chrome://extensions`

**Nothing happens when clicking:**
- Remove and re-add the extension
- Check for errors: click "Errors" on the extension card in `chrome://extensions`

**Service worker errors:**
- Remove the extension completely
- Close and reopen Chrome
- Load the extension again as unpacked

## Mobile / Tablet (Bookmarklet)

Chrome extensions don't work on mobile, but you can use a bookmarklet instead.

### Setup

1. Create a new bookmark (any page)
2. Edit the bookmark
3. Set the name to "Extract Paragraphs"
4. Replace the URL with this code:

```
javascript:(function(){var t=document.querySelector('h1')?document.querySelector('h1').innerText:document.title;var p=document.querySelectorAll('p');var h=Array.from(p).map(function(p){return'<p>'+p.innerHTML+'</p>'}).join('');document.head.innerHTML='<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{max-width:800px;margin:40px auto;padding:0 20px;font-family:Georgia,serif;line-height:1.6;color:#333}h1{margin-bottom:1em;border-bottom:1px solid #ccc;padding-bottom:0.5em}p{margin-bottom:1em}a{color:#0066cc}.back{position:fixed;top:10px;right:10px;padding:8px 16px;background:#0066cc;color:#fff;border:none;border-radius:4px}</style>';document.body.innerHTML='<button class="back" onclick="history.back()">← Back</button><h1>'+t+'</h1>'+h})();
```

### Usage

1. Navigate to any article
2. Open your bookmarks and tap "Extract Paragraphs"
3. The page transforms to show only paragraphs
4. Tap "← Back" button (top right) to return to original page

### Mobile Tips

- **Android Chrome**: Tapping bookmarks from the menu won't work. Instead, type the bookmark name in the address bar and select it from suggestions.
- **iOS Safari**: Add bookmark via Share menu, then edit to replace URL
- **Firefox Mobile**: Supports bookmarklets directly
