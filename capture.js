/**
 * capture.js
 * Captures the animated logo frame-by-frame using Puppeteer + CDP animation
 * time-seeking, then encodes all frames into an MP4 using ffmpeg-static.
 *
 * CDP approach: animations are paused immediately after load, then each frame
 * seeks every animation to its exact target time. Capture speed is irrelevant.
 */

const puppeteer = require('puppeteer');
const path      = require('path');
const fs        = require('fs');
const { spawnSync } = require('child_process');

// ── Config ────────────────────────────────────────────────────────────────────
const HTML_FILE    = path.join(__dirname, 'index.html');
const FRAMES_DIR   = path.join(__dirname, 'frames');
const OUTPUT_MP4   = path.join(__dirname, 'bukhara-logo.mp4');
const FPS          = 30;
const DURATION     = 20;          // seconds
const TOTAL_FRAMES = FPS * DURATION;  // 600
const WIDTH        = 820;
const HEIGHT       = 820;
// ─────────────────────────────────────────────────────────────────────────────

function log(msg) {
  process.stdout.write(msg + '\n');
}

function progress(current, total) {
  const pct = Math.floor((current / total) * 100);
  const bar = '\u2588'.repeat(Math.floor(pct / 2)) + '\u2591'.repeat(50 - Math.floor(pct / 2));
  process.stdout.write(`\r  [${bar}] ${pct}%  frame ${current}/${total}`);
}

// ── Phase 1: Capture frames ───────────────────────────────────────────────────
async function captureFrames() {
  // Prepare clean frames directory
  if (fs.existsSync(FRAMES_DIR)) fs.rmSync(FRAMES_DIR, { recursive: true });
  fs.mkdirSync(FRAMES_DIR);

  log('\n  Launching browser...');

  const browser = await puppeteer.launch({
    headless: true,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-web-security',
      '--allow-file-access-from-files',
      '--disable-features=IsolateOrigins,site-per-process',
      '--force-device-scale-factor=1',
      '--disable-background-timer-throttling',
      '--disable-backgrounding-occluded-windows',
      '--disable-renderer-backgrounding',
    ]
  });

  const page = await browser.newPage();
  await page.setViewport({ width: WIDTH, height: HEIGHT, deviceScaleFactor: 1 });

  const fileUrl = `file:///${HTML_FILE.replace(/\\/g, '/')}`;

  // ── First pass: prime the cache (loads Pexels images, fonts, SVGs) ──
  log('  Loading page and fetching remote assets (first pass)...');
  await page.goto(fileUrl, { waitUntil: 'networkidle2', timeout: 90000 });
  await new Promise(r => setTimeout(r, 3000));
  log('  Assets loaded. Setting up CDP animation control...');

  // ── Open a CDP session and enable Animation domain ──
  const client = await page.target().createCDPSession();
  await client.send('Animation.enable');

  // ── Second load: from cache; pause animations immediately after DOM ready ──
  await page.goto(fileUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });

  // Pause all animations at playback rate 0 before any frame renders
  await client.send('Animation.setPlaybackRate', { playbackRate: 0 });

  // Give JS (particles, etc.) time to initialise without advancing animations
  await new Promise(r => setTimeout(r, 500));

  log(`  Capturing ${TOTAL_FRAMES} frames @ ${FPS}fps (${DURATION}s)...\n`);

  const t0 = Date.now();

  for (let i = 0; i < TOTAL_FRAMES; i++) {
    const framePath = path.join(FRAMES_DIR, `frame-${String(i).padStart(4, '0')}.png`);
    const targetMs  = (i / FPS) * 1000;

    // Seek every Web Animation on the page to exactly targetMs
    await page.evaluate((t) => {
      document.getAnimations().forEach(anim => {
        // startTime is the document-timeline ms when the animation's active
        // phase begins — equivalent to the CSS animation-delay value.
        // Setting currentTime to (t - startTime) correctly places the anim:
        //   negative  → still in delay phase (hidden / not yet started)
        //   0+        → active phase at the right position
        if (anim.startTime !== null) {
          anim.currentTime = t - anim.startTime;
        } else {
          // Animation hasn't started yet; force it into delay phase
          anim.currentTime = t;
        }
      });
    }, targetMs);

    await page.screenshot({
      path: framePath,
      type: 'png',
      clip: { x: 0, y: 0, width: WIDTH, height: HEIGHT }
    });

    progress(i + 1, TOTAL_FRAMES);
  }

  const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
  log(`\n\n  All ${TOTAL_FRAMES} frames captured in ${elapsed}s.`);
  await browser.close();
}

// ── Phase 2: Encode MP4 ───────────────────────────────────────────────────────
function encodeVideo() {
  const ffmpegBin = require('ffmpeg-static');
  const inputPat  = path.join(FRAMES_DIR, 'frame-%04d.png');
  const musicPath = path.join(__dirname, 'geoffharvey-indian-ambience-382991.mp3');
  const hasMusic  = fs.existsSync(musicPath);

  if (hasMusic) {
    log('  Music file found -> will mix audio into MP4...');
  } else {
    log('  No music.mp3 found -> encoding video only (place music.mp3 in project folder to add audio).');
  }

  log('  Encoding MP4 with ffmpeg...');

  const args = [
    '-y',
    '-framerate', String(FPS),
    '-i', inputPat,
  ];

  if (hasMusic) {
    // Seek to middle of the music file so the best part plays over the video
    let musicOffset = 0;
    try {
      const probe = spawnSync(ffmpegBin, ['-i', musicPath], { stdio: ['ignore', 'pipe', 'pipe'] });
      const output = (probe.stderr || '').toString();
      const match  = output.match(/Duration:\s*(\d+):(\d+):([\d.]+)/);
      if (match) {
        const totalSec = parseInt(match[1]) * 3600 + parseInt(match[2]) * 60 + parseFloat(match[3]);
        musicOffset = totalSec / 2;
        log(`  Music duration: ${totalSec.toFixed(1)}s  →  starting at ${musicOffset.toFixed(1)}s (midpoint)`);
      }
    } catch (e) { /* ignore probe errors, start from beginning */ }

    args.push('-ss', String(musicOffset.toFixed(3)), '-stream_loop', '-1', '-i', musicPath);
  }

  args.push(
    '-c:v', 'libx264',
    '-preset', 'slow',
    '-crf', '16',
    '-pix_fmt', 'yuv420p',
    '-movflags', '+faststart',
    '-vf', `scale=${WIDTH}:${HEIGHT}`
  );

  if (hasMusic) {
    args.push(
      '-c:a', 'aac',
      '-b:a', '192k',
      '-af', `afade=t=in:st=0:d=1.5,afade=t=out:st=${DURATION - 2}:d=2`,
      '-shortest'
    );
  }

  args.push(OUTPUT_MP4);

  const result = spawnSync(ffmpegBin, args, { stdio: ['ignore', 'pipe', 'pipe'] });

  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error('ffmpeg failed:\n' + (result.stderr || '').toString());
  }

  const size = (fs.statSync(OUTPUT_MP4).size / 1024 / 1024).toFixed(2);
  log(`  Encoded -> ${OUTPUT_MP4}  (${size} MB)${hasMusic ? '  [with audio]' : ''}`);
}

// ── Cleanup ───────────────────────────────────────────────────────────────────
function cleanup() {
  if (fs.existsSync(FRAMES_DIR)) {
    fs.rmSync(FRAMES_DIR, { recursive: true });
    log('  Temp frames deleted.');
  }
}

// ── Main ──────────────────────────────────────────────────────────────────────
(async () => {
  const t0 = Date.now();
  try {
    await captureFrames();
    encodeVideo();
    cleanup();
    const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
    log(`\n  Done in ${elapsed}s  ->  bukhara-logo.mp4\n`);
  } catch (err) {
    log('\n  Error: ' + err.message);
    cleanup();
    process.exit(1);
  }
})();
