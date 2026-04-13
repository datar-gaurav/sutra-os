/**
 * Run with Node.js to generate the PNG icons needed by the extension:
 *   node generate_icons.js
 *
 * Requires: npm install canvas  (or: npx canvas)
 * If you don't have canvas available, any 16×16, 48×48, and 128×128
 * PNG images placed in icons/ will work fine.
 */

const { createCanvas } = require("canvas");
const fs = require("fs");
const path = require("path");

const SIZES = [16, 48, 128];
const OUT_DIR = path.join(__dirname, "icons");

function drawIcon(size) {
  const canvas = createCanvas(size, size);
  const ctx = canvas.getContext("2d");

  // Background: rounded rectangle with gradient
  const radius = size * 0.2;
  ctx.beginPath();
  ctx.moveTo(radius, 0);
  ctx.lineTo(size - radius, 0);
  ctx.quadraticCurveTo(size, 0, size, radius);
  ctx.lineTo(size, size - radius);
  ctx.quadraticCurveTo(size, size, size - radius, size);
  ctx.lineTo(radius, size);
  ctx.quadraticCurveTo(0, size, 0, size - radius);
  ctx.lineTo(0, radius);
  ctx.quadraticCurveTo(0, 0, radius, 0);
  ctx.closePath();

  const grad = ctx.createLinearGradient(0, 0, size, size);
  grad.addColorStop(0, "#3b82f6");
  grad.addColorStop(1, "#8b5cf6");
  ctx.fillStyle = grad;
  ctx.fill();

  // Letter "S"
  ctx.fillStyle = "#ffffff";
  ctx.font = `bold ${Math.round(size * 0.6)}px Arial`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText("S", size / 2, size / 2 + size * 0.04);

  return canvas.toBuffer("image/png");
}

fs.mkdirSync(OUT_DIR, { recursive: true });

for (const size of SIZES) {
  const outPath = path.join(OUT_DIR, `icon${size}.png`);
  fs.writeFileSync(outPath, drawIcon(size));
  console.log(`Generated ${outPath}`);
}

console.log("Icons generated successfully.");
