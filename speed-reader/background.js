chrome.action.onClicked.addListener(async (tab) => {
  if (tab.url.startsWith("chrome://") || tab.url.startsWith("edge://") || tab.url.startsWith("about:")) {
    console.log("Cannot run on browser internal pages.");
    return;
  }

  try {
    // Try to send a message first to see if it's already injected
    await chrome.tabs.sendMessage(tab.id, { action: "toggle_reader" });
  } catch (err) {
    // If it fails, it means the content script isn't there yet, so we inject it!
    await chrome.scripting.insertCSS({
      target: { tabId: tab.id },
      files: ["content.css"]
    });
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["content.js"]
    });
    // Now that it's injected, it will initialize automatically, but we also send the toggle command
    // Actually, wait! The content.js we wrote doesn't auto-start. Let's send the message after a tiny delay
    // or just let it start. Let's send the message.
    setTimeout(() => {
      chrome.tabs.sendMessage(tab.id, { action: "toggle_reader" });
    }, 100);
  }
});
