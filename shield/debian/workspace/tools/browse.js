#!/usr/bin/env node
// browse - headless Chromium for the Shield bot: open a page, take screenshots, extract text.
//
//   tools/browse flights "<search>" [--pages N]     Google Flights search, e.g.
//        tools/browse flights "Zurich to Rome on 2026-11-07 one way, 2 adults"
//   tools/browse shot <url> [--pages N] [--wait-text REGEX] [--full]
//
// Prints JSON: {url, title, screenshots: [paths], text}. Screenshots go to
// /root/workspace/screenshots (older than a day are deleted). Cookie banners are
// declined (the privacy-preserving choice). Exit code 1 on failure.
const fs = require('fs');
const path = require('path');
const puppeteer = require(path.join(__dirname, 'node_modules', 'puppeteer-core'));

const OUT_DIR = '/root/workspace/screenshots';
const VIEWPORT = { width: 1100, height: 1400 };

function parseArgs(argv) {
  const [mode, target, ...rest] = argv;
  const opts = { mode, target, pages: mode === 'flights' ? 2 : 1, waitText: null, full: false };
  for (let i = 0; i < rest.length; i++) {
    if (rest[i] === '--pages') opts.pages = Math.max(1, Math.min(5, parseInt(rest[++i], 10) || 1));
    else if (rest[i] === '--wait-text') opts.waitText = rest[++i];
    else if (rest[i] === '--full') opts.full = true;
  }
  return opts;
}

function usage() {
  console.error('usage: browse flights "<search>" [--pages N]\n       browse shot <url> [--pages N] [--wait-text REGEX] [--full]');
  process.exit(2);
}

function cleanOld() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const dayAgo = Date.now() - 24 * 3600 * 1000;
  for (const f of fs.readdirSync(OUT_DIR)) {
    const p = path.join(OUT_DIR, f);
    try { if (fs.statSync(p).mtimeMs < dayAgo) fs.unlinkSync(p); } catch (_) {}
  }
}

// Decline cookie/consent banners: Google's consent page and common "reject" buttons.
async function declineConsent(page) {
  for (let attempt = 0; attempt < 2; attempt++) {
    const clicked = await page.evaluate(() => {
      const re = /^(reject all|decline all|decline|reject|only necessary|necessary only|refuse all|alle ablehnen|tout refuser|rifiuta tutto)$/i;
      const el = [...document.querySelectorAll('button, [role=button], input[type=submit]')]
        .find(b => re.test((b.innerText || b.value || '').trim()));
      if (el) { el.click(); return true; }
      return false;
    }).catch(() => false);
    if (!clicked) return false;
    await page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 20000 }).catch(() => {});
    if (!page.url().includes('consent.')) return true;
  }
  return true;
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  if (!opts.target || !['flights', 'shot'].includes(opts.mode)) usage();
  let url = opts.target;
  if (opts.mode === 'flights') {
    url = 'https://www.google.com/travel/flights?q=' + encodeURIComponent('Flights ' + opts.target) + '&hl=en&curr=EUR';
    opts.waitText = opts.waitText || '(€|CHF|\\$)\\s?\\d';
  } else if (!/^https?:\/\//.test(url)) {
    url = 'https://' + url;
  }
  cleanOld();

  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/chromium',
    headless: true,
    // Lean settings: the Shield has little RAM and Claude runs at the same time.
    args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--no-first-run',
           '--disable-extensions', '--disable-background-networking', '--renderer-process-limit=1',
           '--disable-features=site-per-process,IsolateOrigins,Translate,MediaRouter,OptimizationHints',
           '--js-flags=--max-old-space-size=256', '--lang=en-US'],
    defaultViewport: VIEWPORT,
    protocolTimeout: 60000,
  });
  try {
    const page = await browser.newPage();
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 90000 });
    await declineConsent(page);
    if (opts.waitText) {
      const re = opts.waitText;
      await page.waitForFunction((r) => new RegExp(r).test(document.body ? document.body.innerText : ''),
        { timeout: 45000, polling: 1000 }, re).catch(() => {});
    } else {
      await page.waitForNetworkIdle({ idleTime: 1500, timeout: 20000 }).catch(() => {});
    }
    await new Promise(r => setTimeout(r, 2500));                // let late content settle
    await declineConsent(page);                                 // banners that appear late

    const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    const shots = [];
    const warnings = [];
    // One screenshot, with a time limit and one retry; failures don't abort the run.
    const shoot = async (file, extra) => {
      for (let attempt = 1; attempt <= 2; attempt++) {
        try {
          await Promise.race([
            page.screenshot({ path: file, ...extra }),
            new Promise((_, rej) => setTimeout(() => rej(new Error('screenshot timed out after 30 s')), 30000)),
          ]);
          shots.push(file);
          return true;
        } catch (e) {
          if (attempt === 2) warnings.push(`${path.basename(file)}: ${e.message}`);
          await new Promise(r => setTimeout(r, 2000));
        }
      }
      return false;
    };
    if (opts.full) {
      await shoot(path.join(OUT_DIR, `${stamp}-full.png`), { fullPage: true });
    } else {
      for (let i = 0; i < opts.pages; i++) {
        if (i > 0) {
          const moved = await page.evaluate((h) => {
            const before = window.scrollY; window.scrollBy(0, h - 150); return window.scrollY !== before;
          }, VIEWPORT.height).catch(() => false);
          if (!moved) break;
          await new Promise(r => setTimeout(r, 1200));
        }
        if (!await shoot(path.join(OUT_DIR, `${stamp}-${i + 1}.png`), {})) break;
      }
    }
    let text = await page.evaluate(() => document.body ? document.body.innerText : '');
    if (opts.mode === 'flights') {
      // Keep the lines that describe flights (times, durations, stops, prices).
      text = text.split('\n').filter(l => /(\d{1,2}:\d{2}|hr|min|stop|nonstop|€|CHF|\$)/i.test(l)).join('\n');
    }
    console.log(JSON.stringify({
      url: page.url(), title: await page.title(), screenshots: shots,
      ...(warnings.length ? { warnings } : {}),
      text: text.replace(/\n{3,}/g, '\n\n').slice(0, 6000),
    }, null, 2));
  } finally {
    await browser.close().catch(() => {});
  }
}

main().catch(e => { console.error('browse failed: ' + e.message); process.exit(1); });
