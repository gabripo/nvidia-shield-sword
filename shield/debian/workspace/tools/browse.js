#!/usr/bin/env node
// browse - headless Chromium for the Shield bot: open a page, take screenshots, extract text.
//
//   tools/browse flights "<search>" [--pages N]     Google Flights search, e.g.
//        tools/browse flights "Zurich to Rome on 2026-11-07 one way, 2 adults"
//   tools/browse shot <url> [--pages N] [--wait-text REGEX] [--full]
//   tools/browse stop                               close the warm browser now
//
// Chromium stays running ("warm") after a run and is reused by the next one; a
// watchdog closes it after 10 idle minutes to free the RAM.
//
// Prints JSON: {url, title, screenshots: [paths], text}. Screenshots go to
// /root/workspace/screenshots (older than a day are deleted). Cookie banners are
// declined (the privacy-preserving choice). Exit code 1 on failure.
const fs = require('fs');
const path = require('path');
const { spawn, execSync } = require('child_process');
const puppeteer = require(path.join(__dirname, 'node_modules', 'puppeteer-core'));

const OUT_DIR = '/root/workspace/screenshots';
const PORT = 9223;                                   // Chromium's DevTools port (localhost only)
const PROFILE = '/root/.cache/browse-chromium';      // keeps cookie choices between runs
const LAST_USE = '/tmp/browse-last-use';
const IDLE_SECONDS = 600;
const T0 = Date.now();
const dbg = (m) => { if (process.env.BROWSE_DEBUG) console.error(`[${((Date.now() - T0) / 1000).toFixed(1)}s] ${m}`); };
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
  console.error('usage: browse flights "<search>" [--pages N]\n       browse shot <url> [--pages N] [--wait-text REGEX] [--full]\n       browse stop');
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


async function browserUp() {
  try {
    const r = await fetch(`http://127.0.0.1:${PORT}/json/version`, { signal: AbortSignal.timeout(2000) });
    return r.ok;
  } catch (_) { return false; }
}

// Connect to the warm Chromium, or start one (detached, with an idle watchdog).
async function getBrowser() {
  fs.writeFileSync(LAST_USE, String(Date.now()));
  if (await browserUp()) {
    try {
      return await puppeteer.connect({ browserURL: `http://127.0.0.1:${PORT}`, defaultViewport: VIEWPORT,
                                       protocolTimeout: 60000 });
    } catch (_) {
      try { execSync(`pkill -f "^/usr/lib/chromium/chromium .*remote-debugging-port=${PORT}"`); } catch (__) {}   // stale: restart it
      await new Promise(r => setTimeout(r, 1500));
    }
  }
  // Lean settings: the Shield has little RAM and Claude runs at the same time.
  const flags = ['--headless=new', '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--no-first-run',
    '--no-default-browser-check', '--disable-extensions', '--disable-background-networking',
    '--renderer-process-limit=1', '--disable-features=site-per-process,IsolateOrigins,Translate,MediaRouter,OptimizationHints',
    '--js-flags=--max-old-space-size=256', '--lang=en-US', `--remote-debugging-port=${PORT}`,
    '--remote-debugging-address=127.0.0.1', `--user-data-dir=${PROFILE}`, 'about:blank'];
  const q = (a) => "'" + a.replace(/'/g, "'\\''") + "'";
  // The watchdog closes Chromium once LAST_USE is older than IDLE_SECONDS.
  const script = `/usr/bin/chromium ${flags.map(q).join(' ')} >/dev/null 2>&1 & C=$!
    while kill -0 $C 2>/dev/null; do
      sleep 30
      last=$(( $(cat ${LAST_USE} 2>/dev/null || echo 0) / 1000 ))
      [ $(( $(date +%s) - last )) -gt ${IDLE_SECONDS} ] && kill $C
    done`;
  spawn('setsid', ['sh', '-c', script], { detached: true, stdio: 'ignore' }).unref();
  for (let i = 0; i < 40 && !(await browserUp()); i++) await new Promise(r => setTimeout(r, 500));
  return puppeteer.connect({ browserURL: `http://127.0.0.1:${PORT}`, defaultViewport: VIEWPORT, protocolTimeout: 60000 });
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  if (opts.mode === 'stop') {
    try { execSync(`pkill -f "^/usr/lib/chromium/chromium .*remote-debugging-port=${PORT}"`); console.log('warm browser closed'); }
    catch (_) { console.log('no warm browser running'); }
    return;
  }
  if (!opts.target || !['flights', 'shot'].includes(opts.mode)) usage();
  let url = opts.target;
  if (opts.mode === 'flights') {
    url = 'https://www.google.com/travel/flights?q=' + encodeURIComponent('Flights ' + opts.target) + '&hl=en&curr=EUR';
    opts.waitText = opts.waitText || '(€|CHF|\\$)\\s?\\d';
  } else if (!/^https?:\/\//.test(url)) {
    url = 'https://' + url;
  }
  cleanOld();

  const browser = await getBrowser();
  dbg('browser ready');
  try {
    const page = await browser.newPage();
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 90000 });
    dbg('loaded ' + page.url().slice(0, 60));
    await declineConsent(page);
    dbg('consent handled, now at ' + page.url().slice(0, 60));
    if (opts.waitText) {
      const re = opts.waitText;
      await page.waitForFunction((r) => new RegExp(r).test(document.body ? document.body.innerText : ''),
        { timeout: 45000, polling: 1000 }, re).catch(() => {});
    } else {
      await page.waitForNetworkIdle({ idleTime: 1500, timeout: 20000 }).catch(() => {});
    }
    dbg('content wait done');
    await new Promise(r => setTimeout(r, 2500));                // let late content settle
    await declineConsent(page);                                 // banners that appear late

    const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    const shots = [];
    const warnings = [];
    // One screenshot, with a time limit and one retry; failures don't abort the run.
    const shoot = async (file, extra) => {
      for (let attempt = 1; attempt <= 2; attempt++) {
        let timer;
        try {
          await Promise.race([
            page.screenshot({ path: file, ...extra }),
            new Promise((_, rej) => { timer = setTimeout(() => rej(new Error('screenshot timed out after 30 s')), 30000); }),
          ]);
          shots.push(file);
          return true;
        } catch (e) {
          if (attempt === 2) warnings.push(`${path.basename(file)}: ${e.message}`);
          await new Promise(r => setTimeout(r, 2000));
        } finally {
          clearTimeout(timer);       // a pending timer would keep Node alive for 30 s
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
    // Keep the browser warm for the next run: close only our tab, then disconnect.
    for (const pg of await browser.pages().catch(() => [])) {
      if (pg.url() !== 'about:blank') await pg.close().catch(() => {});
    }
    fs.writeFileSync(LAST_USE, String(Date.now()));
    browser.disconnect();
  }
}

main().then(() => { dbg('done'); process.exit(0); })
  .catch(e => { console.error('browse failed: ' + e.message); process.exit(1); });
