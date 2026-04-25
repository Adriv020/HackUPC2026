const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch();
  const page = await browser.newPage();
  await page.setViewport({width: 1400, height: 900});
  await page.goto('file://' + __dirname + '/viz_flex.html', {waitUntil: 'networkidle0'});
  await page.screenshot({path: 'viz_flex_screenshot.png'});
  await browser.close();
})();
