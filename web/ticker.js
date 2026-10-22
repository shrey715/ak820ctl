// Frame clock for music sync. Timers in a hidden tab get throttled to about
// once a second (or worse); a worker's timer keeps ticking, so the lights keep
// moving while you're in another tab.
let timer = null;
self.onmessage = (e) => {
  clearInterval(timer);
  timer = e.data > 0 ? setInterval(() => self.postMessage(0), e.data) : null;
};
