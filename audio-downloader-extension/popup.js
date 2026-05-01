document.addEventListener('DOMContentLoaded', async () => {
  const audioListEl = document.getElementById('audio-list');
  const noAudioEl = document.getElementById('no-audio');
  const downloadAllBtn = document.getElementById('download-all');
  
  let allAudioUrls = new Set();

  try {
    // Get current active tab
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab) return;

    // 1. Get from network requests (background script)
    const storageKey = 'audio_' + tab.id;
    const result = await chrome.storage.local.get(storageKey);
    if (result[storageKey] && Array.isArray(result[storageKey])) {
      result[storageKey].forEach(url => allAudioUrls.add(url));
    }

    // 2. Get from DOM (audio/video tags) via scripting
    const injectionResults = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        const urls = [];
        // Check audio tags
        document.querySelectorAll('audio').forEach(audio => {
          if (audio.src) urls.push(audio.src);
          audio.querySelectorAll('source').forEach(source => {
            if (source.src) urls.push(source.src);
          });
        });
        // Check video tags for audio-only streams or general media
        document.querySelectorAll('video').forEach(video => {
          if (video.src) urls.push(video.src);
          video.querySelectorAll('source').forEach(source => {
            if (source.src) urls.push(source.src);
          });
        });
        return urls;
      }
    });

    if (injectionResults && injectionResults[0] && injectionResults[0].result) {
      injectionResults[0].result.forEach(url => {
        if (url && url.startsWith('http')) {
          allAudioUrls.add(url);
        }
      });
    }

    renderAudioList(Array.from(allAudioUrls));

  } catch (error) {
    console.error("Error fetching audio urls:", error);
  }

  function getFilenameFromUrl(url) {
    try {
      const urlObj = new URL(url);
      const pathname = urlObj.pathname;
      const parts = pathname.split('/');
      let filename = parts[parts.length - 1];
      if (!filename || !filename.includes('.')) {
        filename = 'audio_file.mp3'; // Fallback
      }
      return decodeURIComponent(filename);
    } catch (e) {
      return 'audio_file.mp3';
    }
  }

  function renderAudioList(urls) {
    if (urls.length === 0) {
      noAudioEl.classList.remove('hidden');
      audioListEl.classList.add('hidden');
      downloadAllBtn.classList.add('hidden');
      return;
    }

    noAudioEl.classList.add('hidden');
    audioListEl.classList.remove('hidden');
    downloadAllBtn.classList.remove('hidden');
    
    audioListEl.innerHTML = '';

    urls.forEach((url, index) => {
      const filename = getFilenameFromUrl(url);
      
      const li = document.createElement('li');
      li.className = 'audio-item';
      
      li.innerHTML = `
        <div class="audio-info">
          <span class="audio-name" title="${filename}">${filename}</span>
          <span class="audio-url" title="${url}">${url}</span>
        </div>
        <button class="btn download-btn" data-url="${url}">Download</button>
      `;
      
      audioListEl.appendChild(li);
    });

    // Add event listeners for individual downloads
    document.querySelectorAll('.download-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const url = e.target.getAttribute('data-url');
        downloadUrl(url);
      });
    });
  }

  function downloadUrl(url) {
    chrome.downloads.download({
      url: url,
      filename: getFilenameFromUrl(url),
      saveAs: false
    });
  }

  downloadAllBtn.addEventListener('click', () => {
    Array.from(allAudioUrls).forEach(url => {
      downloadUrl(url);
    });
  });
});
