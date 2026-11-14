// Kiểm thử giao diện feature 003: python3 tests/seed_tools_home.py /tmp/fh3 && FAKE_HOME=/tmp/fh3 node tests/ui_tools.js
const {chromium} = require('playwright');
const {spawn} = require('child_process');
const path = require('path'), fs = require('fs');
const OUT = path.join(__dirname, 'out'); fs.mkdirSync(OUT, {recursive: true});
const HOME = process.env.FAKE_HOME;
const fail = m => { console.error('❌ ' + m); process.exit(1); };
const ok = m => console.log('✓ ' + m);
(async () => {
  const srv = spawn('python3', [path.join(__dirname, '..', 'src', 'don_mac.py'), '--native'],
    {env: {...process.env, HOME}, stdio: ['pipe', 'pipe', 'inherit']});
  const url = await new Promise(r => srv.stdout.on('data', d => { const m = String(d).match(/DONMAC_URL (\S+)/); if (m) r(m[1]); }));
  const b = await chromium.launch();
  for (const scheme of ['light', 'dark']) {
    const p = await b.newPage({viewport: {width: 1240, height: 860}, colorScheme: scheme, deviceScaleFactor: 2});
    const errs = []; p.on('pageerror', e => errs.push(e.message));
    p.on('dialog', d => d.accept());
    await p.goto(url);
    await p.waitForSelector('section', {timeout: 60000});
    await p.click('[data-tab=tools]');
    await p.waitForSelector('#tool-body .tbar', {timeout: 60000});
    if (scheme === 'light') {
      // Gỡ app
      const rows = await p.$$eval('#tool-body .row .name', r => r.map(x => x.textContent));
      if (!rows.some(t => t.includes('Foo'))) fail('Gỡ app thiếu Foo: ' + rows); ok('Gỡ app liệt kê Foo');
      await p.click('#tool-body [data-twhy] >> nth=0');
      const adv = await p.$eval('#tool-body .adv', a => a.textContent);
      if (!adv.includes('Xóa được') || !adv.includes('Vì sao nên cân nhắc')) fail('giải thích app thiếu phần'); ok('bấm nhãn → giải thích app + dữ liệu đi kèm');
      await p.screenshot({path: `${OUT}/tools-apps.png`});
      await p.check('#tool-body input[data-tid]');
      await p.click('[data-tdel=apps]');
      await p.waitForFunction(() => !document.querySelector('#tool-body').textContent.includes('Foo') || document.querySelector('#tool-body .empty'));
      if (!fs.readdirSync(HOME + '/.Trash').includes('Foo.app')) fail('Foo.app không vào Thùng rác'); ok('gỡ Foo → app + dữ liệu vào Thùng rác');
      // Trùng lặp
      await p.click('[data-tool=dupes]');
      await p.click('#tool-body [data-tstart=dupes]');
      await p.waitForSelector('#tool-body section .sh h2', {timeout: 60000});
      const pre = await p.$$eval('#tool-body input[data-tid]:checked', c => c.length);
      if (pre !== 1) fail('nhóm trùng phải tích sẵn đúng 1 bản, thực tế ' + pre);
      if (!(await p.$eval('#tool-body', x => x.textContent)).includes('Đề xuất giữ')) fail('thiếu nhãn Đề xuất giữ');
      ok('Trùng lặp: tích sẵn các bản thừa, có nhãn “Đề xuất giữ”');
      await p.screenshot({path: `${OUT}/tools-dupes.png`});
      // ô chọn cả nhóm (trùng lặp)
      await p.click('#tool-body [data-tclear=dupes]');
      await p.click('#tool-body [data-tgid]');
      if (await p.$$eval('#tool-body input[data-tid]:checked', c => c.length) !== 1) fail('ô nhóm (trùng lặp) phải chọn các bản thừa, giữ bản đề xuất');
      await p.click('#tool-body [data-tgid]');
      if (await p.$$eval('#tool-body input[data-tid]:checked', c => c.length) !== 0) fail('bỏ ô nhóm phải bỏ chọn');
      ok('Trùng lặp: ô chọn cả nhóm bật/tắt các bản thừa');
      await p.click('#tool-body [data-tpick=dupes]');
      await p.click('#tool-body input[data-tid]:not(:checked)');
      await p.click('[data-tdel=dupes]');
      await p.waitForFunction(() => document.querySelector('#toast').style.display === 'block' && document.querySelector('#toast').textContent.includes('ít nhất một bản'));
      ok('chọn hết các bản → bị chặn: “giữ lại ít nhất một bản”');
      // Mồ côi
      await p.click('[data-tool=orphans]');
      await p.waitForSelector('#tool-body .row', {timeout: 60000});
      const orows = await p.$$eval('#tool-body .row .name', r => r.map(x => x.textContent));
      if (!orows.some(t => t.includes('com.gone.app')) || orows.some(t => t.includes('com.test.foo'))) fail('mồ côi sai: ' + orows);
      await p.click('#tool-body [data-twhy] >> nth=0');
      if (!(await p.$eval('#tool-body', x => x.textContent)).includes('Các vị trí')) fail('thiếu danh sách vị trí');
      ok('Dữ liệu mồ côi: có com.gone.app, kèm giải thích + vị trí');
      await p.screenshot({path: `${OUT}/tools-orphans.png`});
      // Ảnh giống (Linux không có sips)
      await p.click('[data-tool=similar]');
      await p.click('#tool-body [data-tstart=similar]');
      await p.waitForSelector('#tool-body .warn, #tool-body .empty', {timeout: 60000});
      ok('Ảnh giống: báo rõ khi máy không có sips');
      // Ảnh giống: ô chọn cả nhóm + nút chọn nhanh (dữ liệu giả vì Linux không có sips)
      await p.evaluate(() => { const f = (i, sz) => ({id: 'f' + i, name: 'img' + i + '.png', path: '/x/img' + i + '.png', size: sz, mtime: 1, preview: 'image', deletable: true, kind: 'PNG'});
        TL.similar.data = {groups: [{gid: 'g1', size: 300, files: [f(1, 200), f(2, 100)]}, {gid: 'g2', size: 90, files: [f(3, 50), f(4, 40)]}], checked: 4}; TL.similar.sel = new Set(); renderTool(); });
      await p.click('#tool-body [data-tgid=g1]');
      if (await p.$$eval('#tool-body input[data-tid]:checked', c => c.length) !== 2) fail('ô nhóm ảnh giống phải chọn mọi ảnh của nhóm');
      await p.click('#tool-body [data-tclear=similar]');
      await p.click('#tool-body [data-tpick=similarAll]');
      if (await p.$$eval('#tool-body input[data-tid]:checked', c => c.length) !== 4) fail('“Chọn tất cả ảnh” phải chọn 4 ảnh');
      await p.click('#tool-body [data-tpick=similarRest]');
      if (await p.$$eval('#tool-body input[data-tid]:checked', c => c.length) !== 2) fail('“trừ ảnh lớn nhất” phải chọn 2 ảnh');
      ok('Ảnh giống: ô chọn cả nhóm, Chọn tất cả ảnh, Chọn trừ ảnh lớn nhất mỗi nhóm');
      // Dấu vết AI
      await p.click('[data-tool=ai]');
      await p.waitForSelector('#tool-body section .sh h2', {timeout: 60000});
      const ai = await p.$eval('#tool-body', x => x.textContent);
      for (const w of ['Claude Code', 'Claude Desktop', 'Codex', '1 phiên bản cũ', 'Transcript phiên làm việc', 'Máy ảo của Cowork']) if (!ai.includes(w)) fail('Dấu vết AI thiếu: ' + w);
      await p.screenshot({path: `${OUT}/tools-ai.png`});
      await p.click('#tool-body [data-tpick=ai]');
      const nsafe = await p.$$eval('#tool-body input[data-tid]:checked', c => c.length);
      if (nsafe < 1) fail('“Chọn mục An toàn” không chọn gì');
      await p.click('#tool-body [data-tclear=ai]');
      await p.click('#tool-body [data-tgrp="Claude Code"]');
      if (await p.$$eval('#tool-body input[data-tid]:checked', c => c.length) < 2) fail('ô nhóm AI không chọn cả nhóm');
      await p.click('#tool-body [data-twhy] >> nth=0');
      if (!(await p.$eval('#tool-body .adv', a => a.textContent)).includes('Xóa được')) fail('giải thích AI thiếu');
      ok('Dấu vết AI: nhóm theo công cụ, chọn An toàn, chọn cả nhóm, giải thích');
      // Luôn giữ
      await p.click('[data-tab=big]');
      await p.waitForSelector('.tr');
      await p.click('.tr:has-text("big.db")');
      if (await p.$eval('#keepBtn', x => x.disabled)) fail('nút Luôn giữ phải bật khi có chọn');
      await p.click('#keepBtn');
      await p.waitForFunction(() => document.querySelector('.tr.lock'));
      ok('Luôn giữ: mục bị khóa ở tab Tệp lớn');
      await p.click('[data-tab=machine]');
      await p.waitForSelector('#m-keep .mini', {timeout: 30000});
      await p.waitForSelector('#m-sec .secrow', {timeout: 30000});
      const mt = await p.$eval('#v-machine', x => x.textContent);
      for (const w of ['Dọn tự động theo lịch', 'Luôn giữ', 'Lịch sử dọn dẹp', 'Trạng thái máy', 'Bảo mật cơ bản', 'Mục tự khởi động'])
        if (!mt.includes(w)) fail('tab Máy & cài đặt thiếu: ' + w);
      await p.click('#m-start [data-gosub=startup]');
      await p.waitForSelector('#o-body [data-oagent], #o-body .mini', {timeout: 30000});
      await p.waitForFunction(() => document.querySelector('#o-body').textContent.includes('com.gone.helper'), null, {timeout: 30000});
      if (!(await p.$eval('#o-body', x => x.textContent)).includes('không còn chương trình')) fail('Khởi động cùng máy thiếu nhãn không còn chương trình');
      await p.click('[data-tab=machine]');
      await p.waitForSelector('#m-keep .mini', {timeout: 30000});
      if (!mt.includes('com.test.foo') && !mt.includes('Foo.app')) { /* lịch sử có ghi lần gỡ Foo */ }
      if (!(await p.$eval('#m-hist', x => x.textContent)).includes('Foo')) fail('lịch sử thiếu lần gỡ Foo');
      ok('tab Máy & cài đặt: lịch, Luôn giữ, lịch sử, trạng thái máy, bảo mật, khởi động');
      await p.screenshot({path: `${OUT}/machine.png`, fullPage: false});
      await p.click('#m-keep [data-unkeep]');
      await p.waitForFunction(() => document.querySelector('#m-keep').textContent.includes('Chưa có mục nào'));
      ok('Bỏ giữ hoạt động');
      if (await p.$eval('.foot', f => f.style.display) !== 'none') fail('thanh dưới phải ẩn ở tab Máy');
      await p.click('[data-tab=suggest]');
      if (await p.$eval('.foot', f => f.style.display) === 'none') fail('thanh dưới phải hiện lại ở tab Đề xuất');
      ok('thanh dưới ẩn/hiện đúng theo tab');
    } else {
      await p.screenshot({path: `${OUT}/tools-dark.png`});
      await p.click('[data-tab=machine]');
      await p.waitForSelector('#m-sec .secrow', {timeout: 30000});
      await p.screenshot({path: `${OUT}/machine-dark.png`});
    }
    if (errs.length) fail('lỗi JS: ' + errs.join(' | '));
    await p.close();
  }
  ok('không có lỗi JS ở chế độ sáng/tối');
  await b.close(); srv.stdin.end();
  console.log('UI TOOLS PASSED');
})().catch(e => { console.error('❌', e.message); process.exit(1); });
