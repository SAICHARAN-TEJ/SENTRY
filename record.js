const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({
    recordVideo: {
      dir: 'brag-output/',
      size: { width: 1920, height: 1080 },
    },
    viewport: { width: 1920, height: 1080 }
  });
  const page = await context.newPage();

  console.log('Navigating to index.html...');
  await page.goto('http://127.0.0.1:8081/index.html');
  
  console.log('Waiting for load...');
  await page.waitForTimeout(4000);

  console.log('Clicking Demo Session...');
  await page.click('#demoSessionBtn');
  await page.waitForTimeout(1000);

  console.log('Clicking Run Job...');
  await page.click('#runJobBtn');
  
  console.log('Waiting for simulation to render...');
  await page.waitForTimeout(6000);

  console.log('Dragging slider...');
  const slider = await page.$('#sliderHandle');
  if (slider) {
    const box = await slider.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 400, box.y + box.height / 2, { steps: 50 });
    await page.mouse.up();
  }
  await page.waitForTimeout(3000);

  console.log('Switching to Metrics tab...');
  await page.click('#tabMetricsBtn');
  await page.waitForTimeout(4000);

  console.log('Switching to Trace tab...');
  await page.click('#tabTraceBtn');
  await page.waitForTimeout(4000);

  console.log('Switching to Alerts tab...');
  await page.click('#tabAlertsBtn');
  await page.waitForTimeout(2000);

  console.log('Opening Dossier...');
  // Try to click the View button, or fallback to calling openDossier
  try {
    const btn = await page.$('button:has-text("Dossier"), button:has-text("View")');
    if (btn) {
      await btn.click();
    } else {
      await page.evaluate(() => {
        if (typeof openDossier === 'function' && typeof allAlerts !== 'undefined' && allAlerts.length > 0) {
          openDossier(allAlerts[0].id);
        } else {
          document.querySelector('.alerts-table button')?.click();
        }
      });
    }
  } catch (e) {
    console.log("Fallback evaluate", e);
  }
  
  await page.waitForTimeout(5000);

  console.log('Closing and saving video...');
  await context.close();
  await browser.close();

  const files = fs.readdirSync('brag-output/');
  for (const file of files) {
    if (file.endsWith('.webm') && file !== 'brag.webm') {
      fs.renameSync(path.join('brag-output', file), path.join('brag-output', 'brag.webm'));
      console.log('Video saved as brag-output/brag.webm');
      break;
    }
  }
})();
