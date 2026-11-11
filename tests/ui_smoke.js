// Kiểm thử giao diện: FAKE_HOME=/tmp/fh node tests/ui_smoke.js
const {chromium} = require('playwright');
const {spawn} = require('child_process');
const path = require('path'), fs = require('fs');
const OUT = path.join(__dirname, 'out'); fs.mkdirSync(OUT, {recursive: true});
const fail = m => { console.error('❌ ' + m); process.exit(1); };
const ok = m => console.log('✓ ' + m);
(async () => {
  const srv = spawn('python3', [path.join(__dirname, '..', 'src', 'don_mac.py'), '--native'],
    {env: {...process.env, HOME: process.env.FAKE_HOME}, stdio: ['pipe', 'pipe', 'inherit']});
  const url = await new Promise(r => srv.stdout.on('data', d => { const m = String(d).match(/DONMAC_URL (\S+)/); if (m) r(m[1]); }));
  const b = await chromium.launch();
  for (const scheme of ['light', 'dark']) {
    const p = await b.newPage({viewport: {width: 1240, height: 820}, colorScheme: scheme, deviceScaleFactor: 2});
    const errs = []; p.on('pageerror', e => errs.push(e.message));
    p.on('dialog', d => d.accept());
    await p.goto(url);
    await p.waitForSelector('section', {timeout: 60000});
    if (scheme === 'light') {
      ok('tab Đề xuất hiện các nhóm');
      const id = await p.$eval('section button.badge[data-why]', b => b.dataset.why);
      const before = await p.$eval(`input[data-id="${id}"]`, i => i.checked);
      await p.click(`section button.badge[data-why="${id}"]`);
      await p.waitForSelector('.adv');
      const txt = await p.$eval('.adv', a => a.textContent);
      if (!txt.includes('Xóa được') || !txt.includes('Vì sao nên cân nhắc')) fail('khung giải thích thiếu phần');
      if (await p.$eval(`input[data-id="${id}"]`, i => i.checked) !== before) fail('bấm nhãn làm đổi ô chọn');
      ok('bấm nhãn → khung “Vì sao?” đủ phần, không đổi lựa chọn');
      const lbl = await p.$$eval('section h2', h => h.map(x => x.textContent).join('|'));
      if (!lbl.includes('Cache trong dữ liệu ứng dụng') || !lbl.includes('Dữ liệu ứng dụng lớn')) fail('thiếu nhóm mới: ' + lbl);
      ok('có nhóm Cache trong dữ liệu app + Dữ liệu app lớn');
      await p.$eval('#v-suggest', v => v.scrollTop = 0);
      await p.screenshot({path: `${OUT}/suggest-why.png`});
    }
    // Tệp lớn
    await p.click('[data-tab=big]');
    await p.waitForSelector('.tr');
    const bigRows = await p.$$eval('.tr', r => r.map(x => x.textContent));
    if (scheme === 'light') {
      if (!bigRows.some(t => t.includes('pycharm'))) fail('Tệp lớn thiếu pycharm .dmg'); ok('Tệp lớn liệt kê .dmg');
      await p.click('[data-sort=name]');
      const names = await p.$$eval('.tr .nm span:nth-child(3)', e => e.map(x => x.textContent));
      const exp = [...names].sort((a, b) => (a.toLowerCase() < b.toLowerCase() ? -1 : 1));
      if (names.join() !== exp.join()) fail('sắp xếp theo tên sai: ' + names); ok('sắp xếp theo Tên');
      await p.click('[data-sort=size]');
      const n50 = await p.$$eval('.tr', r => r.length);
      await p.selectOption('#thr', '10000000');
      const n10 = await p.$$eval('.tr', r => r.length);
      if (!(n10 > n50)) fail(`bộ lọc ngưỡng không đổi số dòng ${n50} → ${n10}`);
      if (!(await p.$$eval('.tr', r => r.map(x => x.textContent))).some(t => t.includes('dep.jar'))) fail('thiếu file trong .gradle');
      ok(`bộ lọc ngưỡng 50 MB → 10 MB: ${n50} → ${n10} dòng, có cả Library/.gradle`);
      await p.click('.tr:has-text("big.db")');
      await p.waitForSelector('.pvsec .adv');
      const pvt = await p.$eval('.pvsec', x => x.textContent);
      if (!pvt.includes('Zalo') || !pvt.includes('Cẩn thận')) fail('khung xem trước thiếu lời khuyên Zalo');
      ok('khung xem trước có “Có nên xóa?” theo từng file');
      await p.screenshot({path: `${OUT}/big-advice.png`});
    }
    await p.click('.tr >> nth=0');
    await p.waitForSelector('#pv video, #pv img, #pv .big');
    if (scheme === 'light') ok('chọn dòng → khung xem trước');
    await p.screenshot({path: `${OUT}/big-${scheme}.png`});
    // Trình duyệt tệp → Pictures → ảnh
    await p.click('[data-tab=browse]');
    await p.waitForSelector('.tr');
    await p.dblclick('.tr:has-text("Pictures")');
    await p.waitForSelector('.crumbs button:has-text("Pictures")');
    await p.click('.tr:has-text("Ảnh kỷ niệm.png")');
    await p.waitForSelector('#pvbox img');
    const w = await p.$eval('#pvbox img', i => new Promise(r => i.complete ? r(i.naturalWidth) : i.onload = () => r(i.naturalWidth)));
    if (w !== 800) fail('ảnh xem trước không tải: ' + w);
    if (scheme === 'light') ok('xem trước ảnh PNG tên tiếng Việt');
    await p.screenshot({path: `${OUT}/browse-image-${scheme}.png`});
    await p.click('.crumbs button:has-text("Thư mục nhà")');
    await p.waitForSelector('.tr:has-text("Documents")');
    await p.dblclick('.tr:has-text("Documents")');
    await p.waitForSelector('.tr:has-text("ghi chú.txt")');
    await p.click('.tr:has-text("ghi chú.txt")');
    await p.waitForFunction(() => (document.getElementById('pvtext') || {}).textContent?.includes('Xin chào'));
    if (scheme === 'light') ok('xem trước văn bản');
    // Library bị khóa
    await p.click('.crumbs button:has-text("Thư mục nhà")');
    await p.waitForSelector('.tr:has-text("Library")');
    const locked = await p.$eval('.tr:has-text("Library") input', i => i.disabled);
    if (!locked) fail('Library không bị khóa'); if (scheme === 'light') ok('Library bị khóa xóa');
    // Bản tải về nhóm
    await p.click('[data-tab=downloads]');
    await p.waitForSelector('.grp');
    const groups = await p.$$eval('.grp', g => g.map(x => x.textContent));
    if (!groups[0].includes('Cũ hơn 1 năm')) fail('nhóm Tải về sai: ' + groups);
    if (scheme === 'light') ok('Bản tải về nhóm theo độ cũ');
    await p.click(scheme === 'light' ? '.tr:has-text("IMG_6091.jpg")' : '.tr >> nth=0');
    await p.waitForSelector('#pvbox');
    await p.screenshot({path: `${OUT}/downloads-${scheme}.png`});
    if (scheme === 'light') {
      // Xóa bằng ⌘⌫ (dialog tự đồng ý)
      await p.keyboard.press('Meta+Backspace');
      await p.waitForFunction(() => !document.querySelector('.tr[data-rid] .nm')?.textContent.includes('IMG_6091') &&
        ![...document.querySelectorAll('.tr')].some(r => r.textContent.includes('IMG_6091')));
      if (!fs.existsSync(path.join(process.env.FAKE_HOME, '.Trash', 'IMG_6091.jpg'))) fail('ảnh không vào Thùng rác');
      ok('⌘⌫ xóa → Thùng rác, biến khỏi bảng');
      // Shift-click chọn nhiều
      await p.click('[data-tab=browse]'); await p.waitForSelector('.tr');
      await p.click('.tr >> nth=0'); await p.click('.tr >> nth=2', {modifiers: ['Shift']});
      const n = await p.$$eval('.tr.sel', r => r.length);
      if (n !== 3) fail('⇧-click chọn ' + n); ok('⇧-click chọn 3 dòng');
      await p.setViewportSize({width: 760, height: 900});
      await p.screenshot({path: `${OUT}/narrow.png`});
    }
    if (errs.length) fail('lỗi JS: ' + errs.join(' | '));
    await p.close();
  }
  await b.close(); srv.stdin.end(); srv.kill();
  console.log('\nUI SMOKE PASSED');
})().catch(e => fail(e.stack || e));
