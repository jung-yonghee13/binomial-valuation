// Streamlit Community Cloud keepalive
// 단순 HTTP ping은 활동으로 집계되지 않으므로, 실제 브라우저로 접속해
// Streamlit 웹소켓(/_stcore/stream) 세션을 일정 시간 유지한다.
// 주의: *.streamlit.app에서 앱은 커뮤니티 클라우드 셸의 iframe(/~/+/) 안에서
// 렌더링되므로, 셀렉터 탐색은 모든 프레임을 순회해야 한다.
import { chromium } from 'playwright';

const APP_URL = process.env.APP_URL || 'https://binomial-valuation-engine.streamlit.app/';
const HOLD_MS = Number(process.env.HOLD_MS || 60000); // 웹소켓 세션 유지 시간
const TIMEOUT_MS = Number(process.env.TIMEOUT_MS || 180000); // 콜드스타트 포함 최대 대기

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await context.newPage();

let wsConnected = false;
page.on('websocket', (ws) => {
  if (ws.url().includes('/_stcore/stream')) {
    wsConnected = true;
    console.log(`[keepalive] websocket open: ${ws.url()}`);
  }
});

async function fail(reason) {
  console.error(`[keepalive] FAIL: ${reason}`);
  await page.screenshot({ path: 'keepalive-failure.png', fullPage: true }).catch(() => {});
  await browser.close();
  process.exit(1);
}

// 모든 프레임에서 셀렉터를 찾는다 (앱이 iframe 안에 있어도 동작)
async function findInFrames(selector) {
  for (const frame of page.frames()) {
    const el = await frame.$(selector).catch(() => null);
    if (el) return { frame, el };
  }
  return null;
}

async function waitInFrames(selector, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const found = await findInFrames(selector);
    if (found) return found;
    await page.waitForTimeout(1000);
  }
  return null;
}

try {
  console.log(`[keepalive] visiting ${APP_URL}`);
  await page.goto(APP_URL, { waitUntil: 'domcontentloaded', timeout: TIMEOUT_MS });

  if (page.url().includes('errors/not_found')) {
    await fail(`no app deployed at ${APP_URL} — check the URL (redirected to not_found)`);
  }
  if (page.url().includes('/-/login')) {
    await fail('app appears private (redirected to /-/login) — set it to public in Streamlit Cloud');
  }

  // 슬립 페이지라면 wake 버튼 클릭 (문구 변경 대비, 프레임 무관 탐색)
  await page.waitForTimeout(5000);
  const wake = await findInFrames('button:has-text("back up"), button:has-text("wake")');
  if (wake) {
    console.log('[keepalive] app is asleep — clicking wake button');
    await wake.el.click();
  }

  // 콜드스타트는 수 분 걸릴 수 있다
  const rendered = await waitInFrames(
    '[data-testid="stApp"], [data-testid="stAppViewContainer"]',
    TIMEOUT_MS,
  );
  if (!rendered) {
    await fail('app did not render within timeout');
  }
  console.log('[keepalive] app rendered');

  // 웹소켓 세션이 활동으로 집계되도록 유지
  await page.waitForTimeout(HOLD_MS);

  if (!wsConnected) {
    await fail('app rendered but /_stcore/stream websocket never opened — visit not counted as activity');
  }

  console.log(`[keepalive] OK — websocket session held for ${HOLD_MS}ms`);
  await browser.close();
  process.exit(0);
} catch (err) {
  await fail(err && err.message ? err.message : String(err));
}
