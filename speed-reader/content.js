let isReaderActive = false;
let words = [];
let currentIndex = 0;
let wpm = 300;
try {
  const savedWpm = localStorage.getItem('speed_reader_wpm');
  if (savedWpm) wpm = parseInt(savedWpm, 10);
} catch (e) {}
let timer = null;
let readerContainer = null;
let wordDisplay = null;
let playPauseBtn = null;
let wpmDisplay = null;
let isPlaying = false;

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "toggle_reader") {
    toggleReader();
  }
});

function toggleReader() {
  if (isReaderActive) {
    cleanupReader();
  } else {
    initReader();
  }
}

function extractText() {
  const sel = window.getSelection().toString();
  if (sel.trim().length > 0) {
      return sel;
  }
  
  // Try to find the main article content
  const article = document.querySelector('article') || document.querySelector('main') || document.body;
  return article.innerText;
}

function initReader() {
  const text = extractText();
  // Split text by whitespace and filter empty strings
  words = text.split(/\s+/).filter(w => w.trim().length > 0);
  currentIndex = 0;

  if (words.length === 0) {
    alert("No text found to read. Try highlighting some text.");
    return;
  }

  isReaderActive = true;
  buildUI();
  updateWordDisplay();
}

function getORP(word) {
  const len = word.length;
  if (len <= 1) return 0;
  if (len <= 5) return 1;
  if (len <= 9) return 2;
  if (len <= 13) return 3;
  return 4;
}

function formatWord(word) {
  const orpIndex = getORP(word);
  const left = word.substring(0, orpIndex);
  const center = word.charAt(orpIndex);
  const right = word.substring(orpIndex + 1);
  
  return `<div class="speed-reader-word-container">
            <span class="speed-reader-left">${left}</span>
            <span class="speed-reader-center">${center}</span>
            <span class="speed-reader-right">${right}</span>
          </div>`;
}

function updateWordDisplay() {
  if (currentIndex >= words.length) {
    pauseReader();
    wordDisplay.innerHTML = formatWord("Done!");
    return;
  }
  const word = words[currentIndex];
  wordDisplay.innerHTML = formatWord(word);
}

function nextWord() {
  currentIndex++;
  updateWordDisplay();
  
  // Calculate delay based on wpm
  if (isPlaying && currentIndex < words.length) {
    let delay = (60 / wpm) * 1000;
    
    // Add a slight extra delay for punctuation, but much less than before
    const word = words[currentIndex - 1]; // previous word
    if (word) {
      if (word.endsWith('.') || word.endsWith('!') || word.endsWith('?')) {
        delay *= 1.3; // Give a slight pause for end of sentences
      } else if (word.endsWith(',') || word.endsWith(';') || word.endsWith(':')) {
        delay *= 1.1; // Very minor pause for commas
      }
    }
    
    timer = setTimeout(nextWord, delay);
  } else if (currentIndex >= words.length) {
    isPlaying = false;
    playPauseBtn.innerText = 'Play';
  }
}

function playReader() {
  isPlaying = true;
  playPauseBtn.innerText = 'Pause';
  if (currentIndex >= words.length) {
    currentIndex = 0; // Restart if at the end
  }
  nextWord();
}

function pauseReader() {
  isPlaying = false;
  playPauseBtn.innerText = 'Play';
  if (timer) {
    clearTimeout(timer);
    timer = null;
  }
}

function togglePlayPause() {
  if (isPlaying) {
    pauseReader();
  } else {
    playReader();
  }
}

function buildUI() {
  readerContainer = document.createElement('div');
  readerContainer.id = 'speed-reader-container';

  const modal = document.createElement('div');
  modal.className = 'speed-reader-modal';

  const closeBtn = document.createElement('button');
  closeBtn.innerText = '×';
  closeBtn.className = 'speed-reader-close';
  closeBtn.onclick = cleanupReader;

  wordDisplay = document.createElement('div');
  wordDisplay.className = 'speed-reader-word-display';

  const controls = document.createElement('div');
  controls.className = 'speed-reader-controls';

  playPauseBtn = document.createElement('button');
  playPauseBtn.innerText = 'Play';
  playPauseBtn.onclick = togglePlayPause;

  const wpmSlider = document.createElement('input');
  wpmSlider.type = 'range';
  wpmSlider.min = '100';
  wpmSlider.max = '1000';
  wpmSlider.step = '25';
  wpmSlider.value = wpm.toString();
  wpmSlider.oninput = (e) => {
    wpm = parseInt(e.target.value, 10);
    wpmDisplay.innerText = `${wpm} WPM`;
    try { localStorage.setItem('speed_reader_wpm', wpm); } catch (e) {}
  };

  wpmDisplay = document.createElement('span');
  wpmDisplay.innerText = `${wpm} WPM`;
  wpmDisplay.className = 'speed-reader-wpm';

  controls.appendChild(playPauseBtn);
  controls.appendChild(wpmSlider);
  controls.appendChild(wpmDisplay);

  modal.appendChild(closeBtn);
  modal.appendChild(wordDisplay);
  modal.appendChild(controls);
  readerContainer.appendChild(modal);

  document.body.appendChild(readerContainer);
  
  // Add keyboard listeners
  document.addEventListener('keydown', handleKeydown);
}

function handleKeydown(e) {
  if (!isReaderActive) return;
  if (e.code === 'Space') {
    e.preventDefault();
    togglePlayPause();
  } else if (e.code === 'Escape') {
    cleanupReader();
  } else if (e.code === 'ArrowLeft') {
    currentIndex = Math.max(0, currentIndex - 10);
    updateWordDisplay();
  } else if (e.code === 'ArrowRight') {
    currentIndex = Math.min(words.length - 1, currentIndex + 10);
    updateWordDisplay();
  }
}

function cleanupReader() {
  pauseReader();
  if (readerContainer && readerContainer.parentNode) {
    readerContainer.parentNode.removeChild(readerContainer);
  }
  document.removeEventListener('keydown', handleKeydown);
  isReaderActive = false;
}
