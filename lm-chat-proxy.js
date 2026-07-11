/* ============================================================================
 * lm-chat-proxy.js  —  private, self-hosted search + deep-read proxy
 * ----------------------------------------------------------------------------
 * Drives ONE real Chromium on YOUR machine / YOUR residential IP.
 *   - No third-party search API, no CORS relay, no Jina. Nothing logs your
 *     queries or the URLs you research. The only requests made are the same
 *     ones your normal browser would make.
 *   - Multi-engine search (DuckDuckGo -> Bing -> Brave) with fallback.
 *   - Reddit threads are read via the native .json endpoint (post + top
 *     comments), which is far richer than scraping the HTML.
 *   - Everything else is rendered in a real browser and cleaned server-side.
 *
 * Wired to the "Local proxy server" provider in LM-chatUI (default port 3456):
 *     GET /search?q=<query>
 *     GET /fetch?url=<url>&q=<optional search query for truncation window>
 *
 * SETUP (one time):
 *     npm init -y
 *     npm i playwright
 *     npx playwright install chromium
 *
 * RUN:
 *     node lm-chat-proxy.js
 *     # optional: HEADFUL=1 node lm-chat-proxy.js   (visible window = least bot-detected)
 *     # optional: PORT=3456  CHANNEL=chrome         (use your installed Chrome)
 *
 * Then in the UI: Settings -> Web Search Provider -> "Local proxy server",
 * Proxy Server URL -> http://localhost:3456
 * ==========================================================================*/

'use strict';

const http = require('http');
const { URL } = require('url');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { spawn } = require('child_process');
// playwright-extra + stealth: patches the fingerprint leaks (webdriver, chrome
// runtime, plugins, WebGL vendor, codecs, and — critically — strips the
// "HeadlessChrome" token and aligns the UA with matching client hints).
const { chromium } = require('playwright-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
chromium.use(StealthPlugin());

const PORT = parseInt(process.env.PORT || '3456', 10);
const HEADFUL = process.env.HEADFUL === '1';
const CHANNEL = process.env.CHANNEL || ''; // e.g. "chrome" to use installed Chrome
const PROFILE_DIR = path.join(__dirname, 'lm-chat-proxy-profile'); // cookies persist here (private, local)
const EXT_DIR = path.join(__dirname, 'lm-chat-proxy-extensions');  // drop unpacked extensions (e.g. uBlock Origin Lite) here
const MAX_CONTENT = 24000;   // chars of page text handed back to the model
const NAV_TIMEOUT = 30000;   // ms per navigation

/* -------------------------------------------------------------- ad-block -- */
// Network-layer protection: abort requests to known ad/tracker/malware-serving
// hosts before the browser ever connects. Works in headless AND headful, can't
// be killed by Chrome's MV2 purge. Extend by dropping a hosts-format
// `blocklist.txt` next to this file (lines: "domain" or "0.0.0.0 domain").
const AD_HOSTS = new Set([
  'doubleclick.net', 'googlesyndication.com', 'googleadservices.com', 'google-analytics.com',
  'googletagmanager.com', 'googletagservices.com', 'adservice.google.com', 'adnxs.com',
  'amazon-adsystem.com', 'adsystem.amazon.com', 'facebook.net', 'connect.facebook.net',
  'scorecardresearch.com', 'quantserve.com', 'quantcount.com', 'taboola.com', 'outbrain.com',
  'criteo.com', 'criteo.net', 'pubmatic.com', 'rubiconproject.com', 'openx.net', 'moatads.com',
  'adform.net', 'casalemedia.com', '33across.com', 'bidswitch.net', 'smartadserver.com',
  'yieldmo.com', 'sharethrough.com', 'adroll.com', 'bluekai.com', 'demdex.net', 'krxd.net',
  'mathtag.com', 'rlcdn.com', 'sundaysky.com', 'teads.tv', 'zergnet.com', 'contextweb.com',
  'serving-sys.com', 'flashtalking.com', 'agkn.com', 'ad.doubleclick.net', 'ads.yahoo.com',
  'analytics.tiktok.com', 'ads-twitter.com', 'hotjar.com', 'mixpanel.com', 'segment.com',
  'branch.io', 'onesignal.com', 'popads.net', 'propellerads.com', 'exoclick.com', 'trafficjunky.com',
]);
(function loadUserBlocklist() {
  try {
    const p = path.join(__dirname, 'blocklist.txt');
    if (!fs.existsSync(p)) return;
    for (let line of fs.readFileSync(p, 'utf8').split('\n')) {
      line = line.trim(); if (!line || line[0] === '#') continue;
      const host = line.split(/\s+/).pop().replace(/^\*\.?/, '');
      if (host && host.includes('.')) AD_HOSTS.add(host.toLowerCase());
    }
  } catch (e) {}
})();
function isBlockedHost(hostname) {
  const h = (hostname || '').toLowerCase();
  const parts = h.split('.');
  for (let i = 0; i < parts.length - 1; i++) {
    if (AD_HOSTS.has(parts.slice(i).join('.'))) return true;
  }
  return false;
}
// Assets a human might need rendered to pass a bot challenge — never abort these.
function isChallengeAsset(url) {
  return /recaptcha|gstatic\.com|hcaptcha|turnstile|challenges\.cloudflare|\/sorry\/|px-captcha|geo\.captcha/i.test(url || '');
}
let _blocked = 0; // count of ad/malware requests aborted (visible via /health)
let _extLoaded = false; // whether unpacked extensions actually got loaded this run

// Discover unpacked extensions (folders containing manifest.json) to load.
function extensionPaths() {
  try {
    if (!fs.existsSync(EXT_DIR)) return [];
    return fs.readdirSync(EXT_DIR)
      .map((d) => path.join(EXT_DIR, d))
      .filter((p) => fs.existsSync(path.join(p, 'manifest.json')));
  } catch (e) { return []; }
}

/* ---------------------------------------------------------------- browser -- */

let _ctx = null;
let _ctxPromise = null;

async function getContext() {
  if (_ctx) return _ctx;
  if (_ctxPromise) return _ctxPromise;
  _ctxPromise = (async () => {
    const opts = {
      headless: !HEADFUL,
      viewport: { width: 1280, height: 900 },
      // No userAgent override: real Chrome (channel) reports a self-consistent
      // UA + Sec-CH-UA client hints; stealth strips "Headless" for bundled
      // Chromium. Forcing a stale UA string is itself a detection signal.
      locale: 'en-US',
      timezoneId: 'America/New_York',
      chromiumSandbox: true, // keep the OS sandbox ON (removes the "--no-sandbox / security will suffer" banner)
      args: ['--disable-blink-features=AutomationControlled'],
    };
    if (CHANNEL) opts.channel = CHANNEL;
    // Extensions load only headful + persistent AND only in Chromium / Chrome for
    // Testing. Stable Google Chrome disabled the --load-extension switch in 2025,
    // so with CHANNEL=chrome they will NOT load. Drop CHANNEL to use bundled
    // Chromium if you want the extension; otherwise the network blocklist covers you.
    const exts = extensionPaths();
    _extLoaded = false;
    if (exts.length && HEADFUL) {
      if (/^chrome($|-)/i.test(CHANNEL)) {
        console.warn(`[proxy] ${exts.length} extension(s) present, but CHANNEL=${CHANNEL} (stable Chrome) blocks --load-extension `
          + '— they will NOT load. Run start-proxy-ext.cmd (bundled Chromium) to load them, or rely on the network blocklist.');
      } else {
        opts.args.push(`--disable-extensions-except=${exts.join(',')}`, `--load-extension=${exts.join(',')}`);
        opts.ignoreDefaultArgs = ['--disable-extensions'];
        _extLoaded = true;
        console.log(`[proxy] loading extension(s): ${exts.map((p) => path.basename(p)).join(', ')}`);
      }
    } else if (exts.length && !HEADFUL) {
      console.warn(`[proxy] ${exts.length} extension(s) found but extensions need headful (start-proxy-ext.cmd).`);
    }
    let ctx;
    try {
      ctx = await chromium.launchPersistentContext(PROFILE_DIR, opts);
    } catch (e) {
      if (CHANNEL) {
        console.warn(`[proxy] channel="${CHANNEL}" failed (${e.message}); using bundled chromium`);
        delete opts.channel;
        ctx = await chromium.launchPersistentContext(PROFILE_DIR, opts);
      } else {
        throw e;
      }
    }
    // Ad/malware blocking + speed. Always abort blocklisted hosts. Skip
    // images/media/fonts ONLY in headless (pure text extraction). In headful a
    // human may need to SEE the page — captchas, image challenges — so load
    // everything. Challenge assets (recaptcha/hcaptcha/cloudflare) are never
    // skipped even in headless, so image captchas can still render if shown.
    await ctx.route('**/*', (route) => {
      const req = route.request();
      let host = '';
      try { host = new URL(req.url()).hostname; } catch (e) {}
      if (isBlockedHost(host)) { _blocked++; return route.abort(); }
      const t = req.resourceType();
      if (!HEADFUL && (t === 'image' || t === 'media' || t === 'font') && !isChallengeAsset(req.url())) {
        return route.abort();
      }
      return route.continue();
    });
    // (webdriver / chrome-runtime / plugins / WebGL evasions are applied by the
    //  stealth plugin per page — no manual patching needed here.)
    _ctx = ctx;
    console.log(`[proxy] browser ready (${HEADFUL ? 'headful' : 'headless'}${CHANNEL ? ', channel=' + CHANNEL : ''})`);
    return ctx;
  })();
  return _ctxPromise;
}

async function withPage(fn) {
  const ctx = await getContext();
  const page = await ctx.newPage();
  page.setDefaultTimeout(NAV_TIMEOUT);
  try {
    return await fn(page);
  } finally {
    await page.close().catch(() => {});
  }
}

/* -------------------------------------------------------------- classify -- */

function classifySource(url) {
  let host = '';
  try { host = new URL(url).hostname.replace(/^www\./, ''); } catch { return {}; }
  const NEWS = ['reuters.com', 'apnews.com', 'bloomberg.com', 'wsj.com', 'ft.com',
    'nytimes.com', 'bbc.co.uk', 'bbc.com', 'theguardian.com', 'cnbc.com',
    'arstechnica.com', 'techcrunch.com', 'theverge.com'];
  if (/\.gov(\.|$)|\.edu(\.|$)/.test(host)) return { source_type: 'official', reliability: 'high' };
  if (host === 'reddit.com' || host.endsWith('.reddit.com')) return { source_type: 'forum', reliability: 'low' };
  if (host === 'news.ycombinator.com' || /stackoverflow\.com|stackexchange\.com/.test(host))
    return { source_type: 'forum', reliability: 'medium' };
  if (host === 'wikipedia.org' || host.endsWith('.wikipedia.org')) return { source_type: 'reference', reliability: 'medium' };
  if (NEWS.includes(host)) return { source_type: 'news', reliability: 'high' };
  return {};
}

/* ---------------------------------------------------------------- search -- */

// Each engine: navigate, then extract [{title,url,snippet}] in-page.
const ENGINES = [
  {
    name: 'duckduckgo',
    url: (q) => 'https://html.duckduckgo.com/html/?kl=us-en&q=' + encodeURIComponent(q),
    parse: () => {
      const out = [];
      document.querySelectorAll('.result').forEach((el) => {
        if (out.length >= 8 || el.classList.contains('result--ad')) return;
        const a = el.querySelector('.result__a');
        if (!a) return;
        let href = a.getAttribute('href') || '';
        const m = href.match(/[?&]uddg=([^&]+)/);
        if (m) { try { href = decodeURIComponent(m[1]); } catch (e) {} }
        if (href.startsWith('//')) href = 'https:' + href;
        if (!/^https?:/.test(href)) return;
        out.push({
          title: a.textContent.trim(),
          url: href,
          snippet: (el.querySelector('.result__snippet') || {}).textContent?.trim() || '',
        });
      });
      return out;
    },
  },
  {
    name: 'bing',
    url: (q) => 'https://www.bing.com/search?setmkt=en-US&q=' + encodeURIComponent(q),
    parse: () => {
      const out = [];
      document.querySelectorAll('li.b_algo').forEach((el) => {
        if (out.length >= 8) return;
        const a = el.querySelector('h2 a');
        if (!a || !/^https?:/.test(a.href)) return;
        const sn = el.querySelector('.b_caption p, .b_algoSlug, p');
        out.push({ title: a.textContent.trim(), url: a.href, snippet: sn ? sn.textContent.trim() : '' });
      });
      return out;
    },
  },
  {
    name: 'brave',
    url: (q) => 'https://search.brave.com/search?source=web&q=' + encodeURIComponent(q),
    parse: () => {
      const out = [];
      document.querySelectorAll('#results [data-type="web"], #results .snippet').forEach((el) => {
        if (out.length >= 8) return;
        const a = el.querySelector('a[href^="http"]');
        if (!a) return;
        const titleEl = el.querySelector('.title, .snippet-title') || a;
        const sn = el.querySelector('.snippet-description, .snippet-content');
        const title = titleEl.textContent.trim();
        if (!title) return;
        out.push({ title, url: a.href, snippet: sn ? sn.textContent.trim() : '' });
      });
      return out;
    },
  },
];

async function doSearch(query) {
  return withPage(async (page) => {
    let lastErr = null;
    for (const eng of ENGINES) {
      try {
        await page.goto(eng.url(query), { waitUntil: 'domcontentloaded', timeout: NAV_TIMEOUT });
        await page.waitForTimeout(600);
        const html = await page.content();
        if (/unusual traffic|are you a robot|\/sorry\/index|captcha-delivery/i.test(html)) {
          lastErr = new Error(eng.name + ' returned a challenge page');
          continue;
        }
        const results = await page.evaluate(eng.parse);
        if (results && results.length) {
          return results.slice(0, 8).map((r) => ({ ...r, ...classifySource(r.url) }));
        }
        lastErr = new Error(eng.name + ' returned 0 results');
      } catch (e) {
        lastErr = e;
      }
    }
    throw lastErr || new Error('all engines failed');
  });
}

/* ----------------------------------------------------------------- reddit -- */

function isReddit(u) {
  try {
    const h = new URL(u).hostname.replace(/^www\./, '');
    return h === 'reddit.com' || h.endsWith('.reddit.com');
  } catch { return false; }
}

function redditJsonUrl(u) {
  const url = new URL(u);
  url.hostname = 'old.reddit.com'; // old.reddit is far more lenient than www for .json
  url.pathname = url.pathname.replace(/\/+$/, '');
  if (!url.pathname.endsWith('.json')) url.pathname += '.json';
  url.searchParams.set('raw_json', '1');
  url.searchParams.set('limit', '60');
  return url.toString();
}

function redditHtmlUrl(u) {
  const url = new URL(u);
  url.hostname = 'old.reddit.com';
  url.pathname = url.pathname.replace(/\.json$/, '').replace(/\/+$/, '') || '/';
  return url.toString();
}

async function fetchReddit(u, page) {
  // Step 1: navigate a REAL page to old.reddit. This passes Reddit's bot check
  // and sets session cookies. Step 2: fetch the .json from INSIDE that page so
  // it looks like Reddit's own same-origin XHR (avoids the 403 you get from a
  // bare request). Step 3: if JSON still refuses, scrape the loaded HTML.
  const htmlUrl = redditHtmlUrl(u);
  const jsonUrl = redditJsonUrl(u);
  await page.goto(htmlUrl, { waitUntil: 'domcontentloaded', timeout: NAV_TIMEOUT });
  await page.waitForTimeout(500);

  const grab = await page.evaluate(async (ju) => {
    try {
      const r = await fetch(ju, { headers: { Accept: 'application/json' }, credentials: 'include' });
      if (!r.ok) return { ok: false, status: r.status };
      return { ok: true, text: await r.text() };
    } catch (e) { return { ok: false, status: 0, err: String(e) }; }
  }, jsonUrl);

  if (grab.ok) {
    try { return formatRedditData(JSON.parse(grab.text), u); }
    catch { /* fall through to HTML scrape */ }
  }
  // Fallback: scrape the old.reddit HTML we already loaded.
  return scrapeRedditHtml(page, htmlUrl);
}

function formatRedditData(data, u) {
  const lines = [];
  const outline = [];

  // Comments thread => [postListing, commentListing]
  if (Array.isArray(data) && data[0]?.data?.children?.[0]?.data?.title) {
    const post = data[0].data.children[0].data;
    lines.push(`# ${post.title}`);
    lines.push(`r/${post.subreddit} · u/${post.author} · score ${post.score} · ${post.num_comments} comments`);
    if (post.selftext) lines.push('\n' + post.selftext.trim());
    lines.push('\n## Top comments\n');
    outline.push({ level: 1, heading: post.title.slice(0, 80) }, { level: 2, heading: 'Top comments' });

    const flat = [];
    const walk = (children, depth) => {
      for (const c of children || []) {
        if (c.kind !== 't1' || !c.data || c.data.body == null) continue;
        flat.push({ depth, author: c.data.author, score: c.data.score || 0, body: c.data.body.trim() });
        if (c.data.replies && c.data.replies.data) walk(c.data.replies.data.children, depth + 1);
      }
    };
    walk(data[1]?.data?.children, 0);
    flat.sort((a, b) => (a.depth - b.depth) || (b.score - a.score));
    for (const c of flat.slice(0, 40)) {
      const indent = '  '.repeat(Math.min(c.depth, 4));
      lines.push(`${indent}- u/${c.author} (${c.score}): ${c.body.replace(/\n+/g, ' ')}`);
    }
    return { title: post.title, url: `https://www.reddit.com${post.permalink}`, content: lines.join('\n'),
      date: new Date(post.created_utc * 1000).toISOString().slice(0, 10),
      source_type: 'forum', reliability: 'low', _section_outline: outline };
  }

  // Listing (search / subreddit) => data.data.children of t3 posts
  const children = data?.data?.children || [];
  const posts = children.filter((c) => c.kind === 't3').map((c) => c.data);
  lines.push(`Reddit listing — ${posts.length} posts`);
  outline.push({ level: 1, heading: 'Reddit listing' });
  for (const p of posts.slice(0, 25)) {
    lines.push(`\n• ${p.title}`);
    lines.push(`  r/${p.subreddit} · u/${p.author} · score ${p.score} · ${p.num_comments} comments`);
    lines.push(`  https://www.reddit.com${p.permalink}`);
    if (p.selftext) lines.push('  ' + p.selftext.trim().replace(/\n+/g, ' ').slice(0, 300));
  }
  return { title: 'Reddit listing', url: u, content: lines.join('\n'),
    source_type: 'forum', reliability: 'low', _section_outline: outline };
}

// Fallback: parse the old.reddit HTML DOM (stable, classic markup).
async function scrapeRedditHtml(page, htmlUrl) {
  const data = await page.evaluate(() => {
    const txt = (el) => (el ? el.textContent.trim() : '');
    const score = (el) => txt(el.querySelector('.score.unvoted')) || txt(el.querySelector('.score'));
    // Comments page: a single post + comment tree
    const commentArea = document.querySelector('.commentarea');
    const mainThing = document.querySelector('#siteTable .thing.link');
    if (commentArea && mainThing) {
      const title = txt(mainThing.querySelector('a.title'));
      const self = txt(mainThing.querySelector('.expando .md, .usertext-body .md'));
      const comments = [];
      commentArea.querySelectorAll('.comment').forEach((c) => {
        if (comments.length >= 40) return;
        const body = txt(c.querySelector(':scope > .entry .md'));
        if (!body) return;
        let depth = 0, p = c.parentElement;
        while (p && p !== commentArea) { if (p.classList && p.classList.contains('child')) depth++; p = p.parentElement; }
        comments.push({ depth, author: txt(c.querySelector(':scope > .entry .author')),
          score: txt(c.querySelector(':scope > .entry .score')), body });
      });
      return { kind: 'thread', title, self, comments };
    }
    // Listing page
    const posts = [];
    document.querySelectorAll('#siteTable .thing.link').forEach((t) => {
      if (posts.length >= 25) return;
      const a = t.querySelector('a.title');
      if (!a) return;
      posts.push({ title: txt(a), url: a.href, subreddit: txt(t.querySelector('.subreddit')),
        author: txt(t.querySelector('.author')), score: score(t),
        comments: txt(t.querySelector('.comments')) });
    });
    return { kind: 'listing', posts };
  });

  const lines = [];
  const outline = [];
  if (data.kind === 'thread') {
    lines.push(`# ${data.title}`);
    if (data.self) lines.push('\n' + data.self);
    lines.push('\n## Top comments\n');
    outline.push({ level: 1, heading: (data.title || '').slice(0, 80) }, { level: 2, heading: 'Top comments' });
    for (const c of data.comments) {
      const indent = '  '.repeat(Math.min(c.depth, 4));
      lines.push(`${indent}- u/${c.author} (${c.score}): ${c.body.replace(/\n+/g, ' ')}`);
    }
    return { title: data.title, url: htmlUrl, content: lines.join('\n'),
      source_type: 'forum', reliability: 'low', _section_outline: outline, via: 'old.reddit html' };
  }
  lines.push(`Reddit listing — ${data.posts.length} posts`);
  outline.push({ level: 1, heading: 'Reddit listing' });
  for (const p of data.posts) {
    lines.push(`\n• ${p.title}`);
    lines.push(`  ${p.subreddit} · u/${p.author} · ${p.score} · ${p.comments}`);
    lines.push(`  ${p.url}`);
  }
  if (!data.posts.length) throw new Error('Reddit returned no parseable content (may be private, quarantined, or blocked).');
  return { title: 'Reddit listing', url: htmlUrl, content: lines.join('\n'),
    source_type: 'forum', reliability: 'low', _section_outline: outline, via: 'old.reddit html' };
}

/* ------------------------------------------------------------------ fetch -- */

// In-page extraction of readable content + headings + candidate dates.
function extractInPage() {
  const clone = document.cloneNode(true);
  clone.querySelectorAll(
    'script,style,noscript,svg,iframe,nav,footer,header,form,aside,[aria-hidden="true"],' +
    '[class*="cookie"],[class*="banner"],[class*="advert"],[id*="advert"]'
  ).forEach((el) => el.remove());

  const cands = [];
  clone.querySelectorAll('article, main, [role="main"], body').forEach((el) => {
    const txt = el.innerText || '';
    cands.push({ el, len: txt.length });
  });
  cands.sort((a, b) => b.len - a.len);
  const root = (cands[0] && cands[0].el) || clone.body;

  const content = (root.innerText || '')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();

  const outline = [];
  root.querySelectorAll('h1,h2,h3,h4').forEach((h) => {
    if (outline.length >= 25) return;
    const t = (h.textContent || '').trim();
    if (t.length >= 2 && t.length <= 90) outline.push({ level: +h.tagName[1], heading: t });
  });

  const meta = (sel, attr) => { const e = document.querySelector(sel); return e ? e.getAttribute(attr) : ''; };
  const title = meta('meta[property="og:title"]', 'content') || document.title || '';
  const date =
    meta('meta[property="article:published_time"]', 'content') ||
    meta('meta[name="date"]', 'content') ||
    meta('time[datetime]', 'datetime') || '';

  return { title: title.trim(), date: (date || '').slice(0, 10), content, outline };
}

function temporalWarning(text) {
  const dates = [...new Set((text.match(/\b(20[12]\d|19\d\d)[-/](0?[1-9]|1[0-2])[-/](0?[1-9]|[12]\d|3[01])\b/g) || []))];
  const statusy = /\b(incident|outage|resolved|degraded|operational|status|maintenance|ongoing)\b/i.test(text);
  if (dates.length >= 3 && statusy) {
    return { likely_status_page: /operational|degraded|outage|incident/i.test(text), dates_found: dates.slice(0, 8) };
  }
  return null;
}

function truncate(content, query) {
  if (!content || content.length <= MAX_CONTENT) return content;
  if (query) {
    const first = query.toLowerCase().split(/\s+/)[0] || '';
    const idx = content.toLowerCase().indexOf(first);
    if (idx > MAX_CONTENT * 0.6) {
      const start = Math.max(0, idx - Math.floor(MAX_CONTENT / 3));
      return `[...truncated, showing section around "${query}"...]\n\n` +
        content.slice(start, start + MAX_CONTENT) + '\n\n[...remainder truncated...]';
    }
  }
  return content.slice(0, MAX_CONTENT) + `\n\n[...content truncated at ${MAX_CONTENT} chars...]`;
}

/* ------------------------------------------------------------------ ebay -- */

function isEbay(u) {
  try { return /(^|\.)ebay\./i.test(new URL(u).hostname); } catch { return false; }
}
function isEbaySearch(u) {
  try { return isEbay(u) && /\/sch\//i.test(new URL(u).pathname); } catch { return false; }
}

// In-page: parse each result card into {title, price, condition, sold_date, url,...}.
// Resilient to eBay's class churn: tries known card selectors, else groups by
// /itm/ anchors. Reads the dedicated price node so bid counts don't corrupt it.
function ebayExtractInPage() {
  const PRICE = /\$[0-9][0-9,]*(?:\.[0-9]{2})?/;
  const SOLD = /Sold\s+([A-Z][a-z]{2,9}\.?\s+\d{1,2},?\s+\d{4})/;
  const CONDS = ['Brand New', 'New (Other)', 'Open box', 'Excellent - Refurbished',
    'Very Good - Refurbished', 'Good - Refurbished', 'Certified - Refurbished',
    'Seller refurbished', 'Pre-Owned', 'For parts or not working', 'New', 'Used'];

  let cards = Array.from(document.querySelectorAll('li.s-item'));
  if (cards.length < 2) cards = Array.from(document.querySelectorAll('.su-card-container, li.s-card, .s-card'));
  if (cards.length < 2) {
    const seen = new Set(); cards = [];
    document.querySelectorAll('a[href*="/itm/"]').forEach((a) => {
      let el = a;
      for (let i = 0; i < 6 && el; i++) { if (PRICE.test(el.textContent || '')) break; el = el.parentElement; }
      if (el && !seen.has(el)) { seen.add(el); cards.push(el); }
    });
  }

  const items = [];
  const seenIds = new Set();
  for (const card of cards) {
    const a = card.querySelector('a.s-item__link, a[href*="/itm/"]') || card.querySelector('a[href^="http"]');
    if (!a) continue;
    let url = a.href.split('?')[0];
    const idm = a.href.match(/\/itm\/(?:[^/]*\/)?(\d{6,})/);
    const id = idm ? idm[1] : url;
    if (seenIds.has(id)) continue;

    const text = (card.innerText || card.textContent || '').replace(/\s+/g, ' ').trim();

    let title = '';
    const tEl = card.querySelector('.s-item__title, .s-card__title, [role="heading"]');
    if (tEl) title = tEl.textContent;
    if (!title) title = a.textContent;
    title = title.replace(/^New Listing/i, '').replace(/Opens in a new window or tab.*$/i, '')
      .replace(/\s+/g, ' ').trim();
    if (!title || /^shop on ebay$/i.test(title)) continue;

    const pEl = card.querySelector('.s-item__price, .s-card__price, [class*="price" i]');
    const priceText = pEl ? pEl.textContent : text;
    const pm = priceText.match(new RegExp(PRICE.source + '(?:\\s*to\\s*' + PRICE.source + ')?'));
    const price = pm ? pm[0].replace(/\s+/g, ' ') : '';

    const sm = text.match(SOLD);
    const cEl = card.querySelector('.SECONDARY_INFO, .s-item__subtitle, .s-card__subtitle');
    const condText = cEl ? cEl.textContent : text;
    let cond = ''; for (const k of CONDS) { if (condText.includes(k)) { cond = k; break; } }
    const bidsM = text.match(/(\d+)\s+bids?/i);

    items.push({
      title, price, condition: cond, sold_date: sm ? sm[1].replace(/\s+/g, ' ') : '',
      url, best_offer: /best offer/i.test(text), free_shipping: /free (shipping|delivery|postage)/i.test(text),
      bids: bidsM ? +bidsM[1] : null,
    });
    seenIds.add(id);
    if (items.length >= 60) break;
  }
  return items;
}

function priceStats(items) {
  const nums = [];
  for (const it of items) {
    const m = (it.price || '').match(/\$([0-9][0-9,]*(?:\.[0-9]{2})?)/); // low end of any range
    if (m) nums.push(parseFloat(m[1].replace(/,/g, '')));
  }
  if (!nums.length) return null;
  nums.sort((a, b) => a - b);
  const q = (p) => { const i = (nums.length - 1) * p, lo = Math.floor(i), hi = Math.ceil(i);
    return nums[lo] + (nums[hi] - nums[lo]) * (i - lo); };
  const median = q(0.5);
  const mean = nums.reduce((a, b) => a + b, 0) / nums.length;
  const f = (n) => '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  // typical_range = interquartile (25th–75th pct): robust to lone cheap/expensive outliers.
  return { count: nums.length, min: f(nums[0]), median: f(median), mean: f(mean),
    max: f(nums[nums.length - 1]), typical_range: `${f(q(0.25))}–${f(q(0.75))}` };
}

const EBAY_BLOCK = /Checking your browser|Pardon Our Interruption|please verify yourself|px-captcha|Press & Hold|Access to this page has been denied|unusual traffic/i;
const rand = (a, b) => a + Math.random() * (b - a);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Human-ish signals: a little mouse movement + scroll. Anti-bot systems weight
// real pointer/scroll events heavily.
async function humanize(page) {
  try {
    await page.mouse.move(rand(150, 600), rand(150, 450), { steps: Math.floor(rand(4, 9)) });
    await page.waitForTimeout(rand(250, 600));
    await page.mouse.wheel(0, rand(300, 900));
    await page.waitForTimeout(rand(300, 700));
  } catch (e) {}
}

// Per-process throttle so rapid agent calls don't machine-gun eBay into a block.
let _lastEbay = 0;
async function ebayThrottle(minGap = 5000) {
  const wait = _lastEbay + minGap - Date.now();
  if (wait > 0) await sleep(wait);
  _lastEbay = Date.now();
}

// Escalating, human-paced navigation. Loads ALL assets (the challenge JS needs
// them), warms a session via the homepage, and lets the interstitial auto-clear
// — with a long window in headful so a Press&Hold can be solved by you.
async function ebayNavigate(page, target) {
  // Allow eBay's own assets (the challenge needs them) but keep blocking ads/malware.
  await page.route('**/*', (r) => {
    let host = '';
    try { host = new URL(r.request().url()).hostname; } catch (e) {}
    if (isBlockedHost(host)) { _blocked++; return r.abort(); }
    return r.continue();
  });
  await ebayThrottle();
  const solveWait = HEADFUL ? 30000 : 9000;
  for (let attempt = 1; attempt <= 4; attempt++) {
    if (attempt >= 2) {
      // Warm the session like a real visitor before hitting search again.
      await page.goto('https://www.ebay.com/', { waitUntil: 'domcontentloaded', timeout: NAV_TIMEOUT }).catch(() => {});
      await humanize(page);
      await page.waitForTimeout(rand(1200, 2600));
    }
    await page.goto(target, { waitUntil: 'domcontentloaded', timeout: NAV_TIMEOUT });
    await page.waitForSelector('li.s-item, .su-card-container, a[href*="/itm/"]', { timeout: 12000 }).catch(() => {});
    await humanize(page);
    if (!EBAY_BLOCK.test(await page.content())) return;
    // Blocked — wait for the challenge to resolve itself (or for you to solve it).
    if (HEADFUL) console.log('[ebay] interstitial shown — solve it in the window if prompted (waiting)...');
    await page.waitForFunction(
      () => !/Pardon Our Interruption|Checking your browser|please verify|Press & Hold/i.test(document.body ? document.body.innerText : 'x')
        && document.querySelector('li.s-item, .su-card-container, a[href*="/itm/"]'),
      { timeout: solveWait }
    ).catch(() => {});
    if (!EBAY_BLOCK.test(await page.content())) return;
    if (attempt < 4) await sleep(rand(3000, 6000) * attempt);
  }
  throw new Error('eBay anti-bot persisted after 4 escalating attempts. This is now IP/rate-based, not fingerprint. '
    + 'Options: (1) wait a few minutes, (2) run start-proxy.cmd (HEADFUL) and solve the Press&Hold once — the cookie then '
    + 'persists for quiet headless runs, (3) reduce how rapidly the agent fires eBay searches.');
}

async function fetchEbay(page, target, query) {
  await ebayNavigate(page, target);
  let items = await page.evaluate(ebayExtractInPage);
  if (!items.length) { await page.waitForTimeout(1200); items = await page.evaluate(ebayExtractInPage); }
  if (!items || !items.length) throw new Error('eBay page had no parseable listing cards (markup may have changed or 0 results).');

  // Title-match filter: keep only listings whose title contains EVERY query word.
  // This is what makes model-specific pricing reliable — eBay keyword search
  // returns near-matches (plain 3090s, 4090s, parts) that pollute raw stats.
  const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const qWords = (query || '').toLowerCase().split(/\s+/).filter((w) => w.length >= 2);
  // Obvious non-cards that name the model in their title (waterblocks, brackets,
  // parts listings, empty boxes...). Excluded from the trusted price stat.
  const ACCESSORY = /water\s?block|back\s?plate|bracket|shroud|heat\s?sink|\briser\b|sticker|decal|box only|empty box|for parts|not working|\bas[- ]?is\b|thermal pad|anti[- ]?sag|\bsupport\b|\bscrew|\bcable\b|\bstand\b|\bholder\b|replacement fan/i;
  for (const it of items) {
    const t = it.title.toLowerCase();
    it.match = qWords.length ? qWords.every((w) => new RegExp('\\b' + esc(w) + '\\b').test(t)) : true;
    it.accessory = ACCESSORY.test(it.title);
  }
  const matched = items.filter((it) => it.match && !it.accessory);

  const isSold = /LH_Sold=1|LH_Complete=1/i.test(target);
  const statsAll = priceStats(items);
  const statsMatch = priceStats(matched);
  const lines = [];
  const outline = [{ level: 1, heading: (isSold ? 'eBay sold listings' : 'eBay listings') + (query ? ' — ' + query : '') }];
  lines.push(`[EBAY ${isSold ? 'SOLD ' : ''}LISTINGS]${query ? ' query "' + query + '"' : ''} — ${items.length} items parsed, ${matched.length} clean title-matches (accessories/parts excluded)`);
  outline.push({ level: 2, heading: 'Price summary' });
  if (qWords.length && statsMatch) {
    lines.push(`>> TITLE-MATCHED price (title contains all of: ${qWords.join(', ')}; accessories/parts removed) — TRUST THIS for "${query}":`);
    lines.push(`   n=${statsMatch.count} · median ${statsMatch.median} · typical range ${statsMatch.typical_range} (25–75th pct) · mean ${statsMatch.mean} · full span ${statsMatch.min}–${statsMatch.max}`);
  }
  if (statsAll) {
    lines.push(`   All parsed items (POLLUTED by near-matches/parts — do NOT quote as the model's price): n=${statsAll.count} · median ${statsAll.median} · range ${statsAll.min}–${statsAll.max}`);
  }
  lines.push('NOTE: Prices are exactly as listed. Items marked [✓match] have the query terms in the title; others are near-matches eBay returned.');
  lines.push('');
  outline.push({ level: 2, heading: 'Listings' });
  items.forEach((it, i) => {
    const tag = it.match ? (it.accessory ? '[~part]' : '[✓match]') : '[~near]';
    const tags = [tag, it.price || 'no price', it.condition || 'condition n/a',
      it.sold_date ? 'Sold ' + it.sold_date : (isSold ? 'sold date n/a' : ''),
      it.best_offer ? 'Best Offer' : '', it.bids != null ? it.bids + ' bids' : '', it.free_shipping ? 'free ship' : '']
      .filter(Boolean).join(' | ');
    lines.push(`${i + 1}. ${tags}`);
    lines.push(`   ${it.title}`);
    lines.push(`   ${it.url}`);
  });

  return {
    url: target, title: (isSold ? 'eBay sold: ' : 'eBay: ') + (query || 'listings'),
    content: lines.join('\n'), source_type: 'marketplace', reliability: 'high',
    _section_outline: outline, via: 'ebay structured',
    _ebay_stats: statsMatch || statsAll || undefined, _ebay_stats_all: statsAll || undefined,
  };
}

// Reports the fingerprint the browser actually presents — so you can confirm
// stealth is active and nothing screams "bot". Hit GET /selftest.
async function selfTest() {
  return withPage(async (page) => {
    await page.goto('https://example.com/', { waitUntil: 'domcontentloaded', timeout: NAV_TIMEOUT }).catch(() => {});
    const fp = await page.evaluate(() => {
      let webgl = 'n/a';
      try {
        const gl = document.createElement('canvas').getContext('webgl');
        const dbg = gl.getExtension('WEBGL_debug_renderer_info');
        webgl = gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) + ' / ' + gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL);
      } catch (e) {}
      return {
        userAgent: navigator.userAgent,
        uaDataBrands: navigator.userAgentData ? navigator.userAgentData.brands.map((b) => `${b.brand} ${b.version}`) : null,
        webdriver: navigator.webdriver,
        languages: navigator.languages,
        pluginCount: navigator.plugins.length,
        hasWindowChrome: !!window.chrome,
        webgl,
      };
    });
    const flags = [];
    if (/Headless/i.test(fp.userAgent)) flags.push('UA contains "Headless" — LEAK');
    if (fp.webdriver) flags.push('navigator.webdriver is true — LEAK');
    if (!fp.hasWindowChrome) flags.push('window.chrome missing — suspicious');
    if (!fp.pluginCount) flags.push('0 plugins — suspicious in headless');
    return { mode: (HEADFUL ? 'headful' : 'headless') + (CHANNEL ? '+' + CHANNEL : ''), fingerprint: fp,
      warnings: flags, verdict: flags.length ? 'has tells' : 'looks clean' };
  });
}

async function doFetch(target, query) {
  return withPage(async (page) => {
    if (isReddit(target)) {
      const r = await fetchReddit(target, page);
      r.content = truncate(r.content, query);
      return r;
    }
    if (isEbaySearch(target)) {
      const r = await fetchEbay(page, target, query);
      r.content = truncate(r.content, query);
      return r;
    }
    await page.goto(target, { waitUntil: 'domcontentloaded', timeout: NAV_TIMEOUT });
    await page.waitForTimeout(700);
    const ex = await page.evaluate(extractInPage);
    const content = truncate(ex.content, query);
    const out = {
      url: target,
      title: ex.title,
      date: ex.date || undefined,
      content,
      _section_outline: ex.outline && ex.outline.length ? ex.outline : undefined,
      ...classifySource(target),
    };
    const tw = temporalWarning(ex.content);
    if (tw) out._temporal_warning = tw;
    return out;
  });
}

/* ------------------------------------------------------------------ yt-dlp -- */
// Video/audio download via yt-dlp. Spawned with an args ARRAY and shell:false —
// the URL is never passed through a shell, so it can't inject commands.
const DL_DIR = process.env.DL_DIR || path.join(os.homedir(), 'Downloads', 'lm-chat-downloads');

function resolveExe(name) {
  if (process.env.YTDLP && name === 'yt-dlp') return process.env.YTDLP;
  const exts = process.platform === 'win32' ? ['.exe', '.cmd', ''] : [''];
  const dirs = (process.env.PATH || '').split(path.delimiter);
  for (const dir of dirs) {
    for (const ext of exts) {
      try { const p = path.join(dir, name + ext); if (p && fs.existsSync(p)) return p; } catch (e) {}
    }
  }
  return name; // let the OS resolve it as a last resort
}
const YTDLP = resolveExe('yt-dlp');

function downloadMedia(rawUrl, format, quality) {
  return new Promise((resolve) => {
    let url;
    try { url = new URL(rawUrl); } catch { return resolve({ success: false, error: 'invalid url' }); }
    if (!/^https?:$/.test(url.protocol)) return resolve({ success: false, error: 'only http/https URLs are allowed' });
    try { fs.mkdirSync(DL_DIR, { recursive: true }); } catch (e) {}

    const capNum = parseInt(quality, 10);
    const isBest = !capNum || /^(best|max|high|highest)$/i.test(String(quality).trim());
    const outTmpl = path.join(DL_DIR, '%(title).150B [%(id)s].%(ext)s');
    const args = ['--no-playlist', '--restrict-filenames', '--no-progress', '--no-warnings',
      '-o', outTmpl, '--no-simulate', '--print', 'after_move:filepath'];
    if (format === 'audio') {
      args.push('-x', '--audio-format', 'mp3', '--audio-quality', '0');
    } else {
      // isBest = no height cap => genuine highest available (incl. 4K/8K).
      const sel = isBest ? 'bv*+ba/b' : `bv*[height<=${capNum}]+ba/b[height<=${capNum}]/b`;
      args.push('-f', sel, '--merge-output-format', 'mp4');
    }
    // Authenticate with your browser's cookies so sites don't refuse yt-dlp
    // ("This video is not available" / bot-check). Opt-in via env:
    //   YT_COOKIES=<path to cookies.txt>  OR  YT_COOKIES_BROWSER=chrome|firefox|edge
    if (process.env.YT_COOKIES) args.push('--cookies', process.env.YT_COOKIES);
    else if (process.env.YT_COOKIES_BROWSER) args.push('--cookies-from-browser', process.env.YT_COOKIES_BROWSER);
    args.push('--', url.toString());

    let child;
    try { child = spawn(YTDLP, args, { windowsHide: true }); }
    catch (e) { return resolve({ success: false, error: 'could not start yt-dlp: ' + e.message }); }
    let out = '', err = '';
    const timer = setTimeout(() => { try { child.kill(); } catch (e) {} }, 20 * 60 * 1000);
    child.stdout.on('data', (d) => { out += d.toString(); });
    child.stderr.on('data', (d) => { err += d.toString(); });
    child.on('error', (e) => {
      clearTimeout(timer);
      resolve({ success: false, error: 'yt-dlp not runnable (' + e.message + '). Install it or set YTDLP=<path>.' });
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      if (code !== 0) {
        const tail = err.split('\n').map((s) => s.trim()).filter(Boolean).slice(-3).join(' | ');
        return resolve({ success: false, error: `yt-dlp failed (exit ${code}): ${tail || 'unknown error'}` });
      }
      const file = out.split('\n').map((s) => s.trim()).filter(Boolean).reverse()
        .find((l) => { try { return fs.existsSync(l); } catch (e) { return false; } }) || '';
      let sizeMb = 0;
      if (file) { try { sizeMb = +(fs.statSync(file).size / 1048576).toFixed(1); } catch (e) {} }
      resolve({
        success: true, file, filename: file ? path.basename(file) : '', size_mb: sizeMb,
        dir: DL_DIR, format: format === 'audio' ? 'mp3' : 'mp4', source: url.toString(),
      });
    });
  });
}

/* ------------------------------------------------------------------ server -- */

function send(res, code, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(code, {
    'Content-Type': 'application/json; charset=utf-8',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': '*',
    'Cache-Control': 'no-store',
  });
  res.end(body);
}

const server = http.createServer(async (req, res) => {
  if (req.method === 'OPTIONS') return send(res, 204, {});
  let u;
  try { u = new URL(req.url, `http://localhost:${PORT}`); } catch { return send(res, 400, { success: false, error: 'bad url' }); }

  try {
    if (u.pathname === '/search') {
      const q = u.searchParams.get('q');
      if (!q) return send(res, 400, { success: false, error: 'missing q' });
      console.log(`[search] ${q}`);
      const results = await doSearch(q);
      return send(res, 200, { success: true, results });
    }
    if (u.pathname === '/fetch') {
      const target = u.searchParams.get('url');
      const query = u.searchParams.get('q') || '';
      if (!target) return send(res, 400, { success: false, error: 'missing url' });
      console.log(`[fetch]  ${target}`);
      const out = await doFetch(target, query);
      return send(res, 200, { success: true, ...out });
    }
    if (u.pathname === '/download') {
      const dlUrl = u.searchParams.get('url');
      const format = (u.searchParams.get('format') || 'video').toLowerCase();
      const quality = u.searchParams.get('quality') || 'best';
      if (!dlUrl) return send(res, 400, { success: false, error: 'missing url' });
      console.log(`[download] ${format} ${dlUrl}`);
      return send(res, 200, await downloadMedia(dlUrl, format, quality));
    }
    if (u.pathname === '/selftest') {
      console.log('[selftest]');
      return send(res, 200, { success: true, ...(await selfTest()) });
    }
    if (u.pathname === '/' || u.pathname === '/health') {
      return send(res, 200, { success: true, service: 'lm-chat-proxy',
        mode: (HEADFUL ? 'headful' : 'headless') + (CHANNEL ? '+' + CHANNEL : ''),
        adblock: { blocklisted_hosts: AD_HOSTS.size, requests_blocked: _blocked },
        extensions: { available: extensionPaths().map((p) => path.basename(p)), requested: _extLoaded,
          // Ground truth: a running chrome-extension:// service worker == it actually loaded.
          active_workers: _ctx ? _ctx.serviceWorkers().filter((w) => w.url().startsWith('chrome-extension://')).length : 0 },
        ytdlp: { exe: YTDLP, download_dir: DL_DIR,
          cookies: process.env.YT_COOKIES || (process.env.YT_COOKIES_BROWSER ? 'browser:' + process.env.YT_COOKIES_BROWSER : 'none') },
        endpoints: ['/search?q=', '/fetch?url=&q=', '/download?url=&format=&quality=', '/selftest'] });
    }
    return send(res, 404, { success: false, error: 'not found' });
  } catch (e) {
    console.error('[error]', e.message);
    return send(res, 200, { success: false, error: e.message });
  }
});

server.listen(PORT, () => {
  console.log(`lm-chat-proxy listening on http://localhost:${PORT}`);
  console.log('Set the UI proxy URL to that address. First query warms the browser (a few seconds).');
  getContext().catch((e) => console.error('[proxy] browser launch failed:', e.message));
});

process.on('SIGINT', async () => { try { if (_ctx) await _ctx.close(); } catch {} process.exit(0); });
