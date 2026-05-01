let capturedAudioUrls = {};

chrome.webRequest.onHeadersReceived.addListener(
  function(details) {
    // Check if the response type is media
    if (details.type === 'media') {
      const tabId = details.tabId;
      if (tabId !== -1) {
        if (!capturedAudioUrls[tabId]) {
          capturedAudioUrls[tabId] = new Set();
        }
        capturedAudioUrls[tabId].add(details.url);
        
        // Save to storage
        chrome.storage.local.set({ ['audio_' + tabId]: Array.from(capturedAudioUrls[tabId]) });
      }
    }
  },
  {urls: ["<all_urls>"]},
  ["responseHeaders"]
);

// Clean up when tab is closed
chrome.tabs.onRemoved.addListener(function(tabId) {
  delete capturedAudioUrls[tabId];
  chrome.storage.local.remove('audio_' + tabId);
});

// Clean up on tab update (reload/navigate)
chrome.tabs.onUpdated.addListener(function(tabId, changeInfo) {
  if (changeInfo.status === 'loading') {
    delete capturedAudioUrls[tabId];
    chrome.storage.local.remove('audio_' + tabId);
  }
});
