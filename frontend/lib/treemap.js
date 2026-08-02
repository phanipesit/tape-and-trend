// Squarified treemap layout (Bruls, Huizing & van Wijk 2000).
//
// Recharts ships a <Treemap>, but it owns its own label rendering and gives no
// grip on tile content — and each tile here needs four lines (ticker, name, price,
// change) plus a click target. Laying out the rectangles ourselves is ~40 lines and
// leaves the tiles as ordinary DOM.
//
// "Squarified" is the part that matters: naive slice-and-dice produces slivers that
// are impossible to label or click. This keeps tiles near square by filling a row
// only while doing so improves its worst aspect ratio.

// Worst aspect ratio in a candidate row, given the length of the side it's laid
// along and the value→area scale factor.
function worstRatio(row, side, scale) {
  const areas = row.map((r) => r.value * scale);
  const sum = areas.reduce((s, a) => s + a, 0);
  const max = Math.max(...areas);
  const min = Math.min(...areas);
  if (sum <= 0 || min <= 0 || side <= 0) return Infinity;
  const s2 = sum * sum;
  const l2 = side * side;
  return Math.max((l2 * max) / s2, s2 / (l2 * min));
}

/**
 * @param items [{ value, ...payload }] — value is any positive magnitude; the
 *   caller's units don't matter, only the ratios between them.
 * @returns the same objects with x/y/w/h added, in the given rect.
 */
export function squarify(items, width, height) {
  const out = [];
  let rest = items.filter((i) => i.value > 0).sort((a, b) => b.value - a.value);
  let [x, y, w, h] = [0, 0, width, height];

  while (rest.length && w > 0.5 && h > 0.5) {
    const total = rest.reduce((s, i) => s + i.value, 0);
    const scale = (w * h) / total;
    const side = Math.min(w, h);

    // Grow the row while the worst tile in it keeps getting squarer.
    const row = [rest[0]];
    while (row.length < rest.length) {
      const next = row.concat(rest[row.length]);
      if (worstRatio(next, side, scale) > worstRatio(row, side, scale)) break;
      row.push(rest[row.length]);
    }

    const rowArea = row.reduce((s, r) => s + r.value, 0) * scale;
    if (w >= h) {
      const rowW = rowArea / h;
      let cy = y;
      for (const r of row) {
        const cellH = (r.value * scale) / rowW;
        out.push({ ...r, x, y: cy, w: rowW, h: cellH });
        cy += cellH;
      }
      x += rowW;
      w -= rowW;
    } else {
      const rowH = rowArea / w;
      let cx = x;
      for (const r of row) {
        const cellW = (r.value * scale) / rowH;
        out.push({ ...r, x: cx, y, w: cellW, h: rowH });
        cx += cellW;
      }
      y += rowH;
      h -= rowH;
    }
    rest = rest.slice(row.length);
  }
  return out;
}

// Tile colour. Direction picks the hue (the palette's up/down tokens); magnitude
// picks the alpha, saturating at CAP so one outlier can't wash the board out — a
// 12% mover and a 3% mover both read "strongly green", which is the honest reading
// at a glance.
const CAP = 3;
export const tileColor = (pct) => {
  if (!pct) return "rgba(90,100,120,0.22)"; // dim — flat
  const a = 0.14 + 0.72 * Math.min(Math.abs(pct) / CAP, 1);
  return pct > 0 ? `rgba(46,212,126,${a.toFixed(3)})` : `rgba(255,92,92,${a.toFixed(3)})`;
};
