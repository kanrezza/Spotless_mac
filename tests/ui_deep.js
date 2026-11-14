// Kiểm thử tab Dọn sâu + Nhiệt độ/Mạng/Quyền riêng tư/Hoàn tác (006): FAKE_HOME=/tmp/fhq node tests/ui_deep.js
const {chromium} = require('playwright');
const {spawn} = require('child_process');
const path = require('path'), fs = require('fs');
const OUT = path.join(__dirname, 'out'); fs.mkdirSync(OUT, {recursive: true});
const HOME = process.env.FAKE_HOME || '/tmp/fhq'; fs.rmSync(HOME, {recursive: true, force: true}); fs.mkdirSync(HOME, {recursive: true});
const fail = m => { console.error('❌ ' + m); process.exit(1); };
const ok = m => console.log('✓ ' + m);
(async () => {
  const srv = spawn('python3', [path.join(__dirname, 'act_harness.py'), '--native'], {env: {...process.env, HOME}, stdio: ['pipe', 'pipe', 'inherit']});
  const url = await new Promise(r => srv.stdout.on('data', d => { const m = String(d).match(/DONMAC_URL (\S+)/); if (m) r(m[1]); }));
  const b = await chromium.launch();
  const p = await b.newPage({viewport: {width: 1240, height: 950}, deviceScaleFactor: 2});
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  p.on('dialog', d => d.accept());
  await p.goto(url);

  await p.click('[data-tab=optim]');
  await p.click('[data-osub=thermal]');
  await p.waitForSelector('.pflow', {timeout: 30000});
  const th = await p.$eval('#o-body', x => x.textContent);
  if (!th.includes('68%') || !th.includes('hạ xung')) fail('nhiệt độ thiếu cảnh báo hạ xung: ' + th.slice(0, 200));
  if (!th.includes('Kê máy')) fail('thiếu lời khuyên hạ nhiệt'); ok('Nhiệt độ: báo hạ xung 68% + lời khuyên');
  await p.screenshot({path: `${OUT}/deep-thermal.png`, fullPage: true});

  await p.click('[data-osub=net]');
  await p.waitForSelector('#o-body table.mini', {timeout: 30000});
  const nt = await p.$eval('#o-body', x => x.textContent);
  if (!nt.includes('Brave Browser') || !nt.includes('/giây')) fail('mạng thiếu dữ liệu: ' + nt.slice(0, 200)); ok('Mạng: Brave đứng đầu, có tốc độ/giây');

  await p.click('[data-osub=priv]');
  await p.waitForSelector('#o-body table.mini', {timeout: 30000});
  const pv = await p.$eval('#o-body', x => x.textContent);
  if (!pv.includes('Ghi màn hình') || !pv.includes('Trợ năng') || !pv.includes('app đã gỡ')) fail('quyền riêng tư thiếu: ' + pv.slice(0, 300));
  if (!pv.includes('chỉ ĐỌC')) fail('thiếu ghi chú chỉ đọc'); ok('Quyền riêng tư: ghi màn hình, trợ năng, app đã gỡ');
  await p.screenshot({path: `${OUT}/deep-privacy.png`, fullPage: true});

  await p.click('[data-osub=undo]');
  await p.waitForSelector('[data-oundo]', {timeout: 30000});
  if (!(await p.$eval('#o-body', x => x.textContent)).includes('node_modules (dự án cũ)')) fail('hoàn tác thiếu lần dọn');
  await p.click('[data-oundo]');
  await p.waitForFunction(() => !document.querySelector('[data-oundo]'), null, {timeout: 20000});
  if (!fs.existsSync(HOME + '/Projects/cu/node_modules')) fail('chưa khôi phục về chỗ cũ');
  ok('Hoàn tác: đưa node_modules về đúng chỗ cũ');

  await p.click('[data-tab=tools]');
  await p.click('[data-tool=dev2]');
  await p.click('[data-tstart=dev2]');
  await p.waitForSelector('#tool-body .rows .row', {timeout: 60000});
  const dv = await p.$eval('#tool-body', x => x.textContent);
  for (const w of ['Gradle', 'Android SDK', 'NDK', 'Snapshot', 'npm cache'])
    if (!dv.includes(w)) fail('dọn sâu thiếu: ' + w);
  ok('Dọn sâu: Gradle, Android SDK, NDK, snapshot, npm');
  await p.click('[data-tpick=dev2]');
  const sel = await p.$$eval('#tool-body .rows input[type=checkbox]:checked', x => x.length);
  if (!sel) fail('chọn mục An toàn không hoạt động'); ok('Chọn mục “An toàn”: ' + sel + ' mục');
  await p.click('#tool-body .rows .row .why');
  await p.waitForSelector('.adv .when', {timeout: 10000});
  ok('mỗi mục có “Nên xóa khi nào”');
  await p.screenshot({path: `${OUT}/deep-dev.png`, fullPage: true});
  if (errs.length) fail('lỗi JS: ' + errs.join(' | ')); ok('không có lỗi JS');
  await b.close(); srv.kill(); console.log('UI DEEP PASSED'); process.exit(0);
})().catch(e => fail(e.stack));
