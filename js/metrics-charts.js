/**
 * SUBPIXEL-SENTRY // VALIDATION & METRICS CHART ENGINE
 * High-DPI Canvas charts with glow effects. Zero external dependencies.
 */

class MetricsChartEngine {
  // Chart series colors, indexed by app.js (mono[0..5]).
  static palette = [
    '#4f9cf9', // series 1 — blue
    '#36c98e', // series 2 — green
    '#f0b429', // series 3 — amber
    '#e4574f', // series 4 — red
    '#9b6ef3', // series 5 — purple
    'rgba(255, 255, 255, 0.35)', // reference / dashed
  ];

  constructor() {
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.colors = {
      bg: '#0a0a16',
      grid: 'rgba(255, 255, 255, 0.04)',
      gridAccent: 'rgba(255, 255, 255, 0.08)',
      axis: 'rgba(255, 255, 255, 0.15)',
      text: '#8a8a9a',
      textBright: '#d0d0dd',
    };
    this.fontFamily = "'Inter', -apple-system, BlinkMacSystemFont, sans-serif";
  }

  _setupCanvas(canvasId) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;

    const rect = canvas.parentElement.getBoundingClientRect();
    const w = rect.width || 550;
    const h = 240;

    canvas.width = w * this.dpr;
    canvas.height = h * this.dpr;
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';

    const ctx = canvas.getContext('2d');
    ctx.scale(this.dpr, this.dpr);

    return { ctx, w, h };
  }

  _drawBackground(ctx, w, h) {
    ctx.fillStyle = 'rgba(0, 0, 0, 0.2)';
    ctx.fillRect(0, 0, w, h);
  }

  _drawGrid(ctx, w, h, padding) {
    const { left, right, top, bottom } = padding;
    const plotW = w - left - right;
    const plotH = h - top - bottom;

    ctx.strokeStyle = this.colors.grid;
    ctx.lineWidth = 0.5;

    // Horizontal grid lines
    for (let i = 0; i <= 5; i++) {
      const y = top + (plotH * i / 5);
      ctx.beginPath();
      ctx.moveTo(left, y);
      ctx.lineTo(w - right, y);
      ctx.stroke();
    }

    // Vertical grid lines
    for (let i = 0; i <= 6; i++) {
      const x = left + (plotW * i / 6);
      ctx.beginPath();
      ctx.moveTo(x, top);
      ctx.lineTo(x, h - bottom);
      ctx.stroke();
    }
  }

  renderLineChart(canvasId, config) {
    const setup = this._setupCanvas(canvasId);
    if (!setup) return;
    const { ctx, w, h } = setup;

    const padding = { left: 50, right: 20, top: 15, bottom: 35 };
    const plotW = w - padding.left - padding.right;
    const plotH = h - padding.top - padding.bottom;

    this._drawBackground(ctx, w, h);
    this._drawGrid(ctx, w, h, padding);

    // Calculate data ranges
    let xMin = Infinity, xMax = -Infinity, yMin = Infinity, yMax = -Infinity;
    config.series.forEach(s => {
      s.data.forEach(d => {
        if (d.x < xMin) xMin = d.x;
        if (d.x > xMax) xMax = d.x;
        if (d.y < yMin) yMin = d.y;
        if (d.y > yMax) yMax = d.y;
      });
    });

    // Add padding to y range
    const yRange = yMax - yMin || 1;
    yMin = Math.max(0, yMin - yRange * 0.1);
    yMax = yMax + yRange * 0.1;

    const mapX = (x) => padding.left + ((x - xMin) / (xMax - xMin || 1)) * plotW;
    const mapY = (y) => padding.top + plotH - ((y - yMin) / (yMax - yMin || 1)) * plotH;

    // Draw axes labels
    ctx.font = `500 9px ${this.fontFamily}`;
    ctx.fillStyle = this.colors.text;
    ctx.textAlign = 'center';

    // X-axis labels
    const xSteps = Math.min(6, Math.floor((xMax - xMin)));
    for (let i = 0; i <= xSteps; i++) {
      const val = xMin + (xMax - xMin) * i / xSteps;
      const x = mapX(val);
      ctx.fillText(val.toFixed(val % 1 === 0 ? 0 : 1), x, h - 8);
    }

    // Y-axis labels
    ctx.textAlign = 'right';
    for (let i = 0; i <= 5; i++) {
      const val = yMin + (yMax - yMin) * (5 - i) / 5;
      const y = padding.top + (plotH * i / 5);
      ctx.fillText(val.toFixed(2), padding.left - 6, y + 3);
    }

    // Draw series
    config.series.forEach(series => {
      if (series.data.length < 2) return;

      // Glow effect
      ctx.save();
      ctx.shadowColor = series.color;
      ctx.shadowBlur = 6;
      ctx.strokeStyle = series.color;
      ctx.lineWidth = 1.8;

      if (series.dashed) {
        ctx.setLineDash([4, 4]);
        ctx.shadowBlur = 0;
        ctx.lineWidth = 1;
        ctx.globalAlpha = 0.5;
      }

      ctx.beginPath();
      series.data.forEach((d, i) => {
        const x = mapX(d.x);
        const y = mapY(d.y);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
      ctx.restore();

      // Area fill (subtle)
      if (!series.dashed) {
        ctx.save();
        ctx.globalAlpha = 0.06;
        ctx.fillStyle = series.color;
        ctx.beginPath();
        series.data.forEach((d, i) => {
          const x = mapX(d.x);
          const y = mapY(d.y);
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });
        ctx.lineTo(mapX(series.data[series.data.length - 1].x), padding.top + plotH);
        ctx.lineTo(mapX(series.data[0].x), padding.top + plotH);
        ctx.closePath();
        ctx.fill();
        ctx.restore();
      }

      // Data points
      if (series.data.length <= 20 && !series.dashed) {
        series.data.forEach(d => {
          const x = mapX(d.x);
          const y = mapY(d.y);
          ctx.beginPath();
          ctx.arc(x, y, 2.5, 0, Math.PI * 2);
          ctx.fillStyle = series.color;
          ctx.fill();
        });
      }
    });

    // Draw markers
    if (config.markers) {
      config.markers.forEach(marker => {
        const x = mapX(marker.x);
        ctx.strokeStyle = marker.color;
        ctx.lineWidth = 1;
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        ctx.moveTo(x, padding.top);
        ctx.lineTo(x, padding.top + plotH);
        ctx.stroke();
        ctx.setLineDash([]);

        ctx.font = `600 9px ${this.fontFamily}`;
        ctx.fillStyle = marker.color;
        ctx.textAlign = 'center';
        ctx.fillText(marker.label, x, padding.top - 4);
      });
    }

    // Legend
    ctx.font = `500 9px ${this.fontFamily}`;
    let legendX = padding.left + 8;
    config.series.forEach(series => {
      if (series.dashed) return;
      ctx.fillStyle = series.color;
      ctx.fillRect(legendX, padding.top + 4, 12, 2);
      ctx.fillStyle = this.colors.textBright;
      ctx.textAlign = 'left';
      ctx.fillText(series.label, legendX + 16, padding.top + 8);
      legendX += ctx.measureText(series.label).width + 30;
    });

    // Axis labels
    if (config.xLabel) {
      ctx.font = `500 9px ${this.fontFamily}`;
      ctx.fillStyle = this.colors.text;
      ctx.textAlign = 'center';
      ctx.fillText(config.xLabel, padding.left + plotW / 2, h - 1);
    }
  }

  renderBarChart(canvasId, config) {
    const setup = this._setupCanvas(canvasId);
    if (!setup) return;
    const { ctx, w, h } = setup;

    const padding = { left: 50, right: 20, top: 15, bottom: 45 };
    const plotW = w - padding.left - padding.right;
    const plotH = h - padding.top - padding.bottom;

    this._drawBackground(ctx, w, h);
    this._drawGrid(ctx, w, h, padding);

    const bars = config.bars;
    const maxVal = Math.max(...bars.map(b => b.value)) * 1.2;
    const barWidth = Math.min(60, plotW / bars.length * 0.5);
    const gap = (plotW - barWidth * bars.length) / (bars.length + 1);

    // Y-axis labels
    ctx.font = `500 9px ${this.fontFamily}`;
    ctx.fillStyle = this.colors.text;
    ctx.textAlign = 'right';
    for (let i = 0; i <= 5; i++) {
      const val = maxVal * (5 - i) / 5;
      const y = padding.top + (plotH * i / 5);
      ctx.fillText(val.toFixed(2), padding.left - 6, y + 3);
    }

    // Draw bars
    bars.forEach((bar, i) => {
      const x = padding.left + gap + i * (barWidth + gap);
      const barH = (bar.value / maxVal) * plotH;
      const y = padding.top + plotH - barH;

      // Bar with glow
      ctx.save();
      ctx.shadowColor = bar.color;
      ctx.shadowBlur = 10;

      // Gradient fill
      const grad = ctx.createLinearGradient(x, y, x, padding.top + plotH);
      grad.addColorStop(0, bar.color);
      grad.addColorStop(1, bar.color + '33');
      ctx.fillStyle = grad;

      // Rounded top corners
      const radius = 4;
      ctx.beginPath();
      ctx.moveTo(x + radius, y);
      ctx.lineTo(x + barWidth - radius, y);
      ctx.quadraticCurveTo(x + barWidth, y, x + barWidth, y + radius);
      ctx.lineTo(x + barWidth, padding.top + plotH);
      ctx.lineTo(x, padding.top + plotH);
      ctx.lineTo(x, y + radius);
      ctx.quadraticCurveTo(x, y, x + radius, y);
      ctx.fill();
      ctx.restore();

      // Value label
      ctx.font = `700 11px ${this.fontFamily}`;
      ctx.fillStyle = bar.color;
      ctx.textAlign = 'center';
      ctx.fillText(bar.value.toFixed(2), x + barWidth / 2, y - 6);

      // Bar label (multi-line)
      ctx.font = `500 9px ${this.fontFamily}`;
      ctx.fillStyle = this.colors.text;
      const lines = bar.label.split('\n');
      lines.forEach((line, li) => {
        ctx.fillText(line, x + barWidth / 2, padding.top + plotH + 14 + li * 12);
      });
    });

    // Threshold line
    if (config.thresholdLine) {
      const tl = config.thresholdLine;
      const y = padding.top + plotH - (tl.y / maxVal) * plotH;
      ctx.strokeStyle = tl.color;
      ctx.lineWidth = 1;
      ctx.setLineDash([5, 3]);
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(w - padding.right, y);
      ctx.stroke();
      ctx.setLineDash([]);

      ctx.font = `600 9px ${this.fontFamily}`;
      ctx.fillStyle = tl.color;
      ctx.textAlign = 'right';
      ctx.fillText(tl.label, w - padding.right - 4, y - 4);
    }
  }
}

window.MetricsChartEngine = MetricsChartEngine;
