# Audio Downloader Extension

A modern Chrome extension designed to detect and download audio files playing on any webpage. It uses a dual-pronged approach to ensure it captures as many audio sources as possible.

## How It Works

This extension actively hunts for audio files through two methods:
1. **Network Interception**: The `background.js` script silently listens to all network requests made by your current tab. Any request classified as `media` (like streaming an MP3 or WAV file) is automatically logged in memory.
2. **DOM Scanning**: When you open the extension popup, a content script is injected into the active page to manually search the HTML for any `<audio>` or `<video>` tags and extracts their source (`src`) URLs.

These two lists are combined, deduplicated, and presented in the extension popup for easy downloading.

## Installation

Since this is an unpacked developer extension, you'll need to load it manually in your browser:

1. Open your Chromium-based browser (Chrome, Edge, Brave, etc.).
2. Navigate to your extensions page: `chrome://extensions/` (or `edge://extensions/`).
3. Toggle on **Developer mode** (usually found in the top right corner).
4. Click the **Load unpacked** button.
5. Select the `audio-downloader-extension` directory.
6. The extension is now installed! You may want to pin it to your toolbar for easy access.

## Usage

1. Go to any website containing the audio you want to download.
2. **Important:** Press play on the audio file. The network interceptor requires the browser to actually request the audio file from the server to detect it.
3. Click the **Audio Downloader** icon in your browser toolbar.
4. You will see a list of all detected audio files.
5. Click **Download** next to an individual file, or **Download All** at the bottom.

## Libby and Other Library Download Services
If using at Libby or a similar service, after downloading a segment, you will need to advance past the length of the dowloaded audio file to load the next sequential file in the audiobook. For example if you are downloading a 5 hour audiobook and each file is 1 hour long, you will need to advance past the length of 1 hour to load the next sequential file in the audiobook so that it can be downloaded. The filenames that look like a hash with a part number are the correct ones to download (e.g{EAD42EBE-65F1-4B20-8EF3-E2F28BA15842}Fmt425-Part01.mp4).  Move the files into a folder together and they should play in order using any standard audio player.

## Required Permissions

* `activeTab` & `scripting`: Allows the extension to safely inject a script into the current tab you are viewing to scan the HTML for `<audio>` tags when you open the popup.
* `webRequest`: Allows the background script to monitor network traffic to detect media files loading in the background.
* `storage`: Used to temporarily store the list of detected audio URLs for each tab so they persist when you close and reopen the popup.
* `downloads`: Gives the extension permission to save the audio files directly to your default downloads folder.

## Known Limitations

While this extension handles standard audio files (like `.mp3`, `.wav`, `.ogg`) exceptionally well, modern web platforms sometimes use complex streaming methods that are difficult to capture:
* **Blob URLs**: If a website uses Javascript to construct a `blob:` URL for audio, it cannot be downloaded directly via a standard URL fetch.
* **HLS / DASH Streams**: Platforms like Spotify, Soundcloud, or large video sites often break audio down into tiny chunks (`.m3u8` or `.ts` files) rather than a single file. This extension will detect the chunks, but downloading them individually won't give you a playable song.
* **CORS Restrictions**: Extremely strict Cross-Origin Resource Sharing policies on some servers might block the browser from triggering a programmatic download.
