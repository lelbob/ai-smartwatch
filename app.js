/**
 * Smartwatch Display Engine - Matching Diagram Navigation & Gestures
 * 
 * - Screen 1: Default Tasks View (Time header, Tasks title, 1, 2, 3 list)
 * - Screen 2: Listening View (Active while pressing & holding side button)
 * - Screen 3: Question & Answer View (Question, divider line, Ans, Read Aloud & OK)
 * - "After OK" -> Returns directly to Screen 1
 */

document.addEventListener('DOMContentLoaded', () => {
  const sideBtn = document.getElementById('side-button');
  const timeDisplay = document.getElementById('time-display');
  
  const screen1 = document.getElementById('screen-1');
  const screen2 = document.getElementById('screen-2');
  const screen3 = document.getElementById('screen-3');

  const liveTranscript = document.getElementById('live-transcript');
  const qaQuestion = document.getElementById('qa-question');
  const qaAnswer = document.getElementById('qa-answer');

  const btnReadAloud = document.getElementById('btn-read-aloud');
  const btnOk = document.getElementById('btn-ok');

  let pressTimer = null;
  let isHolding = false;
  let recognition = null;
  let recordedText = '';
  let latestAnswerText = '';

  // --------------------------------------------------------------------------
  // Live Time Header
  // --------------------------------------------------------------------------
  function updateTime() {
    const now = new Date();
    timeDisplay.textContent = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
  }
  updateTime();
  setInterval(updateTime, 5000);

  // --------------------------------------------------------------------------
  // View Switcher (Screen 1, Screen 2, Screen 3)
  // --------------------------------------------------------------------------
  function showScreen(screenEl) {
    [screen1, screen2, screen3].forEach(s => s.classList.remove('active'));
    screenEl.classList.add('active');
  }

  // --------------------------------------------------------------------------
  // Hold-and-Release Button Mechanics (Matching Diagram)
  // --------------------------------------------------------------------------
  const HOLD_MS = 250; // Threshold to differentiate click vs hold

  function onButtonPressStart(e) {
    e.preventDefault();
    sideBtn.classList.add('pressing');
    isHolding = false;

    pressTimer = setTimeout(() => {
      // Button held down -> Open Screen 2 (Listening) and keep active
      isHolding = true;
      showScreen(screen2);
      startSpeechRecognition();
    }, HOLD_MS);
  }

  function onButtonPressEnd(e) {
    e.preventDefault();
    sideBtn.classList.remove('pressing');
    clearTimeout(pressTimer);

    if (isHolding) {
      // Released after holding -> Finish voice recording & process message
      isHolding = false;
      stopSpeechRecognitionAndSend();
    } else {
      // Short click -> Open / Return to Screen 1 (Tasks)
      showScreen(screen1);
    }
  }

  sideBtn.addEventListener('mousedown', onButtonPressStart);
  sideBtn.addEventListener('mouseup', onButtonPressEnd);
  sideBtn.addEventListener('touchstart', onButtonPressStart);
  sideBtn.addEventListener('touchend', onButtonPressEnd);

  // --------------------------------------------------------------------------
  // Speech Recognition (STT) while holding button
  // --------------------------------------------------------------------------
  function startSpeechRecognition() {
    recordedText = '';
    liveTranscript.textContent = 'Listening for speech...';

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      liveTranscript.textContent = 'Speak your question...';
      return;
    }

    try {
      recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = true;

      recognition.onresult = (event) => {
        let text = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          text += event.results[i][0].transcript;
        }
        recordedText = text;
        liveTranscript.textContent = text || 'Listening for speech...';
      };

      recognition.start();
    } catch (err) {
      console.warn(err);
    }
  }

  function stopSpeechRecognitionAndSend() {
    if (recognition) {
      try { recognition.stop(); } catch (e) {}
    }

    const question = recordedText.trim() || "What is the weather today?";
    qaQuestion.textContent = question;
    
    // Simulate query & process answer -> Open Screen 3 (Question & Ans)
    processAIAnswer(question);
  }

  // --------------------------------------------------------------------------
  // Telegram Bot Query Simulation -> Opens Screen 3 (Question & Ans)
  // --------------------------------------------------------------------------
  function processAIAnswer(questionText) {
    qaAnswer.textContent = 'Processing...';
    showScreen(screen3);

    setTimeout(() => {
      let answer = '';
      const lower = questionText.toLowerCase();

      if (lower.includes('weather')) {
        answer = '72°F, Clear Sky. Battery at 98%.';
      } else if (lower.includes('remind') || lower.includes('task')) {
        answer = `Task scheduled! Added "${questionText}" to list.`;
      } else {
        answer = `Athena AI: Answer for "${questionText}" received via SIM data.`;
      }

      latestAnswerText = answer;
      qaAnswer.textContent = answer;
    }, 800);
  }

  // --------------------------------------------------------------------------
  // Screen 3 Action Buttons: [Read Aloud] & [OK] ("After OK" -> Screen 1)
  // --------------------------------------------------------------------------
  
  // Left Button: Read Aloud
  btnReadAloud.addEventListener('click', () => {
    if (latestAnswerText && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel();
      const utt = new SpeechSynthesisUtterance(latestAnswerText);
      window.speechSynthesis.speak(utt);
    }
  });

  // Right Button: OK -> Returns to Screen 1 (Time / Tasks)
  btnOk.addEventListener('click', () => {
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
    // "After OK" arrow in diagram -> Returns to Screen 1 (Tasks)
    showScreen(screen1);
  });
});
