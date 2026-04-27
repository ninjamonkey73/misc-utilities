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
