# Speed Reader

A lightweight speed reading tool inspired by Spritz and Amazon's Wordrunner. It extracts the main text from any article (or specifically highlighted text) and displays it one word at a time in a modal window, helping you focus and read faster. 

The extension intelligently calculates the Optimal Recognition Point (ORP) for each word, keeping your eyes completely stationary.

## Features
- **Dynamic WPM:** Adjust your reading speed seamlessly from 100 to 1000 WPM.
- **Optimal Recognition Point (ORP):** Highlights the ideal center character of each word in red to eliminate eye movement.
- **Smart Pacing:** Adds subtle, natural pauses for punctuation (commas, periods) to make the flow feel more organic.
- **Keyboard Shortcuts:** 
  - `Space` - Play/Pause
  - `Escape` - Close the reader
  - `Left Arrow` - Rewind 10 words
  - `Right Arrow` - Skip forward 10 words

---

## Installation (Chrome Extension)

1. Open Chrome and navigate to `chrome://extensions/`
2. Enable **Developer mode** using the toggle in the top right corner.
3. Click the **Load unpacked** button.
4. Select the `speed-reader` directory.
5. Go to any normal webpage (not a blank tab or a settings page) and click the extension icon to start reading!

---

## Installation (Mobile Bookmarklet)

You can use the exact same tool on mobile devices (iOS Safari, Chrome for Android, etc.) without needing a browser extension by using a Bookmarklet.

### How to set up the Bookmarklet:

1. Open the file `bookmarklet.txt` in this repository and copy the **entire** string of text inside it.
2. Open your mobile browser and bookmark any random webpage.
3. Edit the bookmark you just made.
4. **Change the Name:** Rename it to `Speed Reader` (or whatever you prefer).
5. **Paste the Code:** Delete the URL that is currently there, and paste the entire JavaScript block you copied from `bookmarklet.txt` into the URL field. Save it.

### How to Run it on Mobile

**For iOS Safari:**
Whenever you are on an article on your phone, open your bookmarks list and tap the `Speed Reader` bookmark.

**For Android Chrome (Important!):**
Chrome for Android blocks bookmarklets that are tapped directly from the Bookmarks menu. To run it:
1. Go to an article you want to read.
2. Tap the **Address Bar** (where the URL is) at the top of the screen.
3. Start typing the name of the bookmark (e.g., "Speed Reader").
4. Tap the suggestion in the dropdown list that has a star/bookmark icon next to it. It will instantly execute!
