// Kiểm thử tab Pin & tối ưu (005): FAKE_HOME=/tmp/fhp node tests/ui_optim.js
const {chromium} = require('playwright');
const {spawn} = require('child_process');
const path = require('path'), fs = require('fs');
const OUT = path.join(__dirname, 'out'); fs.mkdirSync(OUT, {recursive: true});
const HOME = process.env.FAKE_HOME || '/tmp/fhp'; fs.rmSync(HOME, {recursive: true, force: true}); fs.mkdirSync(HOME, {recursive: true});
const fail = m => { console.error('❌ ' + m); process.exit(1); };
const ok = m => console.log('✓ ' + m);
(async () => {
  const srv = spawn('python3', [path.join(__dirname, 'act_harness.py'), '--native'], {env: {...process.env, HOME}, stdio: ['pipe', 'pipe', 'inherit']});
  const url = await new Promise(r => srv.stdout.on('data', d => { const m = String(d).match(/DONMAC_URL (\S+)/); if (m) r(m[1]); }));
  const b = await chromium.launch();
  for (const scheme of ['light', 'dark']) {
    const p = await b.newPage({viewport: {width: 1240, height: 900}, colorScheme: scheme, deviceScaleFactor: 2});
    const errs = []; p.on('pageerror', e => errs.push(e.message));
    p.on('dialog', d => d.accept());
    await p.goto(url);
    await p.click('[data-tab=optim]');
    await p.click('[data-osub=power]');
    await p.waitForSelector('.pflow', {timeout: 30000});
    const pw = await p.$eval('#o-body', x => x.textContent);
    if (!pw.includes('TỤT') || !pw.includes('30W') || !pw.includes('33')) fail('Pin & sạc thiếu cảnh báo tụt pin: ' + pw.slice(0, 300)); ok('Pin & sạc: cảnh báo pin tụt, củ 30W, máy dùng 33W');
    if (!pw.includes('Claude') || !pw.includes('Sức khỏe pin') || !pw.includes('86%')) fail('thiếu app tốn điện/sức khỏe pin'); ok('app tốn điện + sức khỏe pin 86%');
    await p.screenshot({path: `${OUT}/optim-power-${scheme}.png`, fullPage: true});
    await p.click('[data-osub=checks]');
    await p.waitForSelector('.ock', {timeout: 20000});
    const ck = await p.$eval('#o-body', x => x.textContent);
    if (!ck.includes('Tiết kiệm bộ nhớ đang tắt') || !ck.includes('chạy nền')) fail('kiểm tra nhanh thiếu Brave: ' + ck.slice(0, 300)); ok('Kiểm tra nhanh: Brave tắt Tiết kiệm bộ nhớ, chạy nền');
    await p.click('[data-osub=startup]');
    await p.waitForSelector('[data-oagent]', {timeout: 20000});
    if (scheme === 'light') {
      await p.click('[data-oagent="com.google.keystone.agent.plist"]');
      await p.waitForFunction(() => document.querySelector('#o-body').textContent.includes('Bật lại'));
      if (fs.existsSync(HOME + '/Library/LaunchAgents/com.google.keystone.agent.plist')) fail('chưa tắt agent'); ok('Tắt trình cập nhật Google → có Bật lại');
      await p.click('[data-oagent="com.google.keystone.agent.plist"]');
      await p.waitForFunction(() => document.querySelector('#o-body').textContent.includes('Tắt'));
      if (!fs.existsSync(HOME + '/Library/LaunchAgents/com.google.keystone.agent.plist')) fail('chưa bật lại'); ok('Bật lại → plist về chỗ cũ');
    }
    await p.click('[data-osub=watch]');
    await p.waitForSelector('#wsave');
    await p.click('[data-osub=trends]');
    await p.waitForSelector('.chart', {timeout: 20000});
    const tr = await p.$eval('#o-body', x => x.textContent);
    if (!tr.includes('Ổ đầy thêm') || !tr.includes('Bộ nhớ đệm') || !tr.includes('Đã dọn theo tuần')) fail('lịch sử thiếu: ' + tr.slice(0, 300));
    ok('Lịch sử: dự báo ổ, ổ đầy vì đâu, đã dọn theo tuần');
    await p.screenshot({path: `${OUT}/optim-trends-${scheme}.png`, fullPage: true});
    if (errs.length) fail('lỗi JS: ' + errs.join(' | ')); ok(`không có lỗi JS (${scheme})`);
    await p.close();
  }
  await b.close(); srv.kill(); console.log('UI OPTIM PASSED'); process.exit(0);
})().catch(e => fail(e.stack));
