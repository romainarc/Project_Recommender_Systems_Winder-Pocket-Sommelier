import { useId } from "react";

// Product-style bottle renderings, drawn in SVG (offline, no image rights).
// The silhouette follows the wine (Bordeaux, Burgundy, Alsace flute, Champagne, half bottle),
// the glass and capsule follow its type, and the label carries the real winery name.

const GLASS = {
  Red: { glass: "#2a0b12", mid: "#4a1220", capsule: "#5c1424", capsule2: "#8a2436", label: "#f6f1e8", ink: "#3a0f19" },
  White: { glass: "#a9b97a", mid: "#d7dfb0", capsule: "#b89c55", capsule2: "#e2c98a", label: "#fbf8f1", ink: "#4a4024" },
  "Rosé": { glass: "#e9a99f", mid: "#f6d3cb", capsule: "#c97c74", capsule2: "#ecb2a9", label: "#fffaf7", ink: "#6b2f2a" },
  Sparkling: { glass: "#1f2a17", mid: "#3b4a2a", capsule: "#b8913b", capsule2: "#f0d488", label: "#f8f2e1", ink: "#3d2f0e" },
  Dessert: { glass: "#8a520f", mid: "#d39a3a", capsule: "#7a4a10", capsule2: "#c9913a", label: "#fbf3e2", ink: "#5a3409" },
  "Dessert/Port": { glass: "#1c0709", mid: "#3a0e14", capsule: "#1f1f1f", capsule2: "#5a5a5a", label: "#efe6d8", ink: "#2a1a10" },
};

// silhouettes on a 120 x 400 canvas (bottom at y = 392)
const SHAPES = {
  bordeaux:
    "M51 8h18v92c0 10 3 15 10 20 9 6 13 14 13 26v236c0 6-4 10-10 10H38c-6 0-10-4-10-10V146c0-12 4-20 13-26 7-5 10-10 10-20z",
  burgundy:
    "M51 8h18v80c0 22 6 40 16 58 6 10 9 20 9 32v214c0 6-4 10-10 10H36c-6 0-10-4-10-10V178c0-12 3-22 9-32 10-18 16-36 16-58z",
  flute:
    "M53 8h14v104c0 26 7 46 12 64 2 8 3 15 3 22v194c0 6-3 10-9 10H47c-6 0-9-4-9-10V198c0-7 1-14 3-22 5-18 12-38 12-64z",
  champagne:
    "M50 8h20v74c0 30 10 50 20 70 5 10 8 20 8 32v198c0 7-5 12-12 12H34c-7 0-12-5-12-12V184c0-12 3-22 8-32 10-20 20-40 20-70z",
  half:
    "M53 60h14v80c0 10 3 15 9 20 7 5 10 12 10 22v200c0 6-4 10-10 10H44c-6 0-10-4-10-10V182c0-10 3-17 10-22 6-5 9-10 9-20z",
};

const FLUTE_GRAPES = ["Riesling", "Gewürztraminer", "Gewurztraminer", "Pinot Gris", "Muscat/Moscato", "Sylvaner"];
const BURGUNDY_GRAPES = ["Pinot Noir", "Chardonnay", "Syrah/Shiraz", "Gamay", "Nebbiolo", "Viognier"];

export function bottleShape(type, grapes = []) {
  if (type === "Sparkling") return "champagne";
  if (type === "Dessert") return "half";
  if (type === "Dessert/Port") return "bordeaux";
  if (grapes.some((g) => FLUTE_GRAPES.includes(g)) || type === "Rosé") return "flute";
  if (grapes.some((g) => BURGUNDY_GRAPES.includes(g)) || type === "White") return "burgundy";
  return "bordeaux";
}

export function bottleColors(type) {
  return GLASS[type] || GLASS.Red;
}

function shorten(text, n) {
  if (!text) return "";
  return text.length > n ? text.slice(0, n - 1).trimEnd() + "…" : text;
}

export default function Bottle({ type = "Red", grapes = [], winery, name, height = 260, reflection = true, label = true }) {
  const id = useId().replace(/:/g, "");
  const c = bottleColors(type);
  const shape = bottleShape(type, grapes);
  const d = SHAPES[shape];
  const half = shape === "half";
  const labelTop = shape === "flute" ? 236 : half ? 250 : 222;
  const labelH = half ? 90 : 104;
  const capH = shape === "champagne" ? 96 : half ? 46 : 64;
  const capTop = half ? 58 : 6;
  const capW = shape === "champagne" ? 24 : shape === "flute" ? 18 : 22;
  const capX = 60 - capW / 2;
  const total = reflection ? 470 : 400;

  return (
    <svg
      viewBox={`0 0 120 ${total}`}
      height={height}
      width={(height * 120) / total}
      role="img"
      aria-hidden="true"
      className="bottle"
    >
      <defs>
        <linearGradient id={`body${id}`} x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" stopColor={c.glass} />
          <stop offset="0.28" stopColor={c.mid} />
          <stop offset="0.42" stopColor={c.glass} />
          <stop offset="0.78" stopColor={c.glass} />
          <stop offset="1" stopColor={c.mid} stopOpacity="0.85" />
        </linearGradient>
        <linearGradient id={`cap${id}`} x1="0" x2="1">
          <stop offset="0" stopColor={c.capsule} />
          <stop offset="0.35" stopColor={c.capsule2} />
          <stop offset="0.6" stopColor={c.capsule} />
          <stop offset="1" stopColor={c.capsule} />
        </linearGradient>
        <linearGradient id={`paper${id}`} x1="0" x2="1">
          <stop offset="0" stopColor={c.label} stopOpacity="0.86" />
          <stop offset="0.3" stopColor={c.label} />
          <stop offset="0.85" stopColor={c.label} />
          <stop offset="1" stopColor={c.label} stopOpacity="0.8" />
        </linearGradient>
        <linearGradient id={`fade${id}`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#fff" stopOpacity="1" />
          <stop offset="0.6" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
        <mask id={`mask${id}`} maskUnits="userSpaceOnUse" x="0" y="396" width="120" height="80">
          <rect x="0" y="396" width="120" height="80" fill={`url(#fade${id})`} />
        </mask>
        <clipPath id={`clip${id}`}>
          <path d={d} />
        </clipPath>
      </defs>

      {/* ground shadow */}
      <ellipse cx="60" cy="394" rx="40" ry="5" fill="#000" opacity="0.18" />

      <g>
        <path d={d} fill={`url(#body${id})`} />
        <g clipPath={`url(#clip${id})`}>
          {/* long specular highlights, like studio light on glass */}
          <rect x="35" y="0" width="5" height="400" fill="#fff" opacity="0.32" />
          <rect x="42" y="0" width="2" height="400" fill="#fff" opacity="0.18" />
          <rect x="84" y="0" width="3" height="400" fill="#fff" opacity="0.12" />
          {/* punt shading at the base */}
          <rect x="0" y="372" width="120" height="30" fill="#000" opacity="0.18" />
          {label && (
            <g>
              <rect x="0" y={labelTop} width="120" height={labelH} fill={`url(#paper${id})`} />
              <rect x="0" y={labelTop + 6} width="120" height="0.8" fill={c.ink} opacity="0.35" />
              <rect x="0" y={labelTop + labelH - 7} width="120" height="0.8" fill={c.ink} opacity="0.35" />
              <text x="60" y={labelTop + 30} textAnchor="middle" fill={c.ink} fontSize="7" letterSpacing="1.4" fontFamily="Georgia, serif">
                {shorten((winery || "").toUpperCase(), 16)}
              </text>
              <line x1="48" x2="72" y1={labelTop + 40} y2={labelTop + 40} stroke={c.ink} strokeWidth="0.6" opacity="0.6" />
              <text x="60" y={labelTop + 58} textAnchor="middle" fill={c.ink} fontSize="9.5" fontStyle="italic" fontFamily="Georgia, serif">
                {shorten(name || "", 17)}
              </text>
              <text x="60" y={labelTop + 76} textAnchor="middle" fill={c.ink} fontSize="5.5" letterSpacing="1.6" opacity="0.75" fontFamily="Helvetica, Arial, sans-serif">
                {(type || "").toUpperCase()}
              </text>
            </g>
          )}
        </g>
        {/* capsule */}
        <rect x={capX} y={capTop} width={capW} height={capH} rx="3" fill={`url(#cap${id})`} />
        <rect x={capX} y={capTop + capH - 6} width={capW} height="2" fill="#000" opacity="0.18" />
      </g>

      {reflection && (
        <g mask={`url(#mask${id})`}>
          <g transform="translate(0 788) scale(1 -1)" opacity="0.2">
            <path d={d} fill={`url(#body${id})`} />
          </g>
        </g>
      )}
    </svg>
  );
}

// A wine glass with a liquid level and tint (used for the "body" question).
export function Glass({ level = 0.5, tint = "#5e1426", height = 120 }) {
  const id = useId().replace(/:/g, "");
  const y = 70 - level * 44;
  return (
    <svg viewBox="0 0 80 140" height={height} width={(height * 80) / 140} aria-hidden="true">
      <defs>
        <clipPath id={`bowl${id}`}>
          <path d="M14 10h52c2 34-6 58-26 62C20 68 12 44 14 10z" />
        </clipPath>
      </defs>
      <g clipPath={`url(#bowl${id})`}>
        <rect x="0" y={y} width="80" height="80" fill={tint} />
        <ellipse cx="40" cy={y} rx="30" ry="2.5" fill="#fff" opacity="0.25" />
      </g>
      <path d="M14 10h52c2 34-6 58-26 62C20 68 12 44 14 10z" fill="none" stroke="#1d1d1f" strokeOpacity="0.55" strokeWidth="1.4" />
      <path d="M20 16c-1 18 2 34 9 44" fill="none" stroke="#fff" strokeOpacity="0.7" strokeWidth="2" strokeLinecap="round" />
      <path d="M40 72v52M24 128h32" stroke="#1d1d1f" strokeOpacity="0.55" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

// A line whose waves get sharper with acidity (soft, balanced, crisp).
export function Wave({ level = 1, height = 56 }) {
  const amp = [6, 11, 16][level - 1] || 6;
  const n = [2, 3, 5][level - 1] || 2;
  const w = 160;
  const pts = [];
  for (let i = 0; i <= 64; i++) {
    const x = (i / 64) * w;
    const y = 30 - amp * Math.sin((i / 64) * Math.PI * 2 * n);
    pts.push(`${x.toFixed(1)},${y.toFixed(1)}`);
  }
  return (
    <svg viewBox={`0 0 ${w} 60`} height={height} width={(height * w) / 60} aria-hidden="true">
      <polyline points={pts.join(" ")} fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
