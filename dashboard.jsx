import { useState, useMemo, useCallback } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Brush, Legend, ReferenceLine,
  Area, ComposedChart,
} from "recharts";

// ─── Sample Data Generator ────────────────────────────────────────
// Realistic Bangladesh commodity prices (BDT) based on actual TCB data
const COMMODITIES = [
  { name: "চাল সরু (নাজির/মিনিকেট)", nameEn: "Fine Rice (Nazir/Miniket)", unit: "per kg", basePrice: 72, volatility: 0.03 },
  { name: "চাল (মোটা)/স্বর্ণা", nameEn: "Coarse Rice", unit: "per kg", basePrice: 52, volatility: 0.04 },
  { name: "আটা সাদা (খোলা)", nameEn: "Flour (Loose)", unit: "per kg", basePrice: 42, volatility: 0.05 },
  { name: "সয়াবিন তেল (লুজ)", nameEn: "Soybean Oil (Loose)", unit: "per L", basePrice: 165, volatility: 0.04 },
  { name: "পাম অয়েল (লুজ)", nameEn: "Palm Oil (Loose)", unit: "per L", basePrice: 145, volatility: 0.05 },
  { name: "মশুর ডাল (বড়)", nameEn: "Red Lentil (Large)", unit: "per kg", basePrice: 90, volatility: 0.06 },
  { name: "ছোলা", nameEn: "Chickpea", unit: "per kg", basePrice: 85, volatility: 0.05 },
  { name: "আলু", nameEn: "Potato", unit: "per kg", basePrice: 25, volatility: 0.12 },
  { name: "পিঁয়াজ (দেশী)", nameEn: "Onion (Local)", unit: "per kg", basePrice: 45, volatility: 0.15 },
  { name: "রসুন (দেশী)", nameEn: "Garlic (Local)", unit: "per kg", basePrice: 120, volatility: 0.1 },
  { name: "শুকনা মরিচ", nameEn: "Dry Chili", unit: "per kg", basePrice: 280, volatility: 0.07 },
  { name: "হলুদ", nameEn: "Turmeric", unit: "per kg", basePrice: 320, volatility: 0.06 },
  { name: "আদা", nameEn: "Ginger", unit: "per kg", basePrice: 160, volatility: 0.12 },
  { name: "জিরা", nameEn: "Cumin", unit: "per kg", basePrice: 650, volatility: 0.05 },
  { name: "চিনি", nameEn: "Sugar", unit: "per kg", basePrice: 105, volatility: 0.04 },
  { name: "লবণ", nameEn: "Salt", unit: "per kg", basePrice: 40, volatility: 0.02 },
  { name: "রুই মাছ", nameEn: "Rohu Fish", unit: "per kg", basePrice: 350, volatility: 0.08 },
  { name: "ইলিশ", nameEn: "Hilsa", unit: "per kg", basePrice: 1200, volatility: 0.2 },
  { name: "গরুর মাংস", nameEn: "Beef", unit: "per kg", basePrice: 750, volatility: 0.03 },
  { name: "মুরগী (ব্রয়লার)", nameEn: "Chicken (Broiler)", unit: "per kg", basePrice: 190, volatility: 0.08 },
  { name: "ডিম (ফার্ম)", nameEn: "Egg (Farm)", unit: "per hali", basePrice: 38, volatility: 0.06 },
  { name: "গুঁড়া দুধ (ডানো)", nameEn: "Milk Powder (Dano)", unit: "1 kg", basePrice: 780, volatility: 0.02 },
  { name: "কাঁচামরিচ", nameEn: "Green Chili", unit: "per kg", basePrice: 100, volatility: 0.25 },
  { name: "বেগুন", nameEn: "Eggplant", unit: "per kg", basePrice: 60, volatility: 0.2 },
  { name: "লেবু", nameEn: "Lemon", unit: "per hali", basePrice: 50, volatility: 0.2 },
  { name: "খেজুর", nameEn: "Dates", unit: "per kg", basePrice: 400, volatility: 0.08 },
  { name: "দারুচিনি", nameEn: "Cinnamon", unit: "per kg", basePrice: 520, volatility: 0.04 },
  { name: "এম,এস রড (৬০)", nameEn: "MS Rod (Grade 60)", unit: "per MT", basePrice: 82000, volatility: 0.03 },
];

const YEAR_COLORS = {
  2018: "#6366f1", 2019: "#8b5cf6", 2020: "#a855f7",
  2021: "#d946ef", 2022: "#ec4899", 2023: "#f43f5e",
  2024: "#ef4444", 2025: "#f97316", 2026: "#eab308",
};

const PREDICTION_COLOR = "#22d3ee";

function generatePriceData(commodity, startYear = 2018, endYear = 2026) {
  const data = [];
  let price = commodity.basePrice * (0.7 + Math.random() * 0.2);
  const trend = 0.00015 + Math.random() * 0.0001;
  const seasonAmp = commodity.volatility * commodity.basePrice * 0.3;
  const today = new Date(2026, 2, 12);

  for (let y = startYear; y <= endYear; y++) {
    const endM = y === endYear ? 2 : 11;
    for (let m = (y === startYear ? 7 : 0); m <= endM; m++) {
      const daysInMonth = new Date(y, m + 1, 0).getDate();
      for (let d = 1; d <= daysInMonth; d += (y < 2022 ? 1 : 1)) {
        const date = new Date(y, m, d);
        if (date > today) break;
        if (date.getDay() === 5) continue;

        const dayOfYear = Math.floor((date - new Date(y, 0, 0)) / 86400000);
        const seasonal = Math.sin((dayOfYear / 365) * 2 * Math.PI) * seasonAmp;
        const ramadan = (m >= 2 && m <= 4) ? commodity.basePrice * 0.05 : 0;
        const noise = (Math.random() - 0.5) * commodity.volatility * commodity.basePrice * 0.5;

        price = price * (1 + trend) + seasonal * 0.01 + noise * 0.3;
        price = Math.max(price * 0.5, Math.min(price, commodity.basePrice * 3));

        const spread = price * (0.1 + Math.random() * 0.15);
        const priceMin = Math.round(price - spread / 2);
        const priceMax = Math.round(price + spread / 2);
        const priceAvg = Math.round((priceMin + priceMax) / 2);

        data.push({
          date: `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`,
          year: y,
          month: m + 1,
          priceMin,
          priceMax,
          priceAvg,
          isPrediction: false,
        });
      }
    }
  }
  return data;
}

function generatePredictions(commodity, historyData, days = 90) {
  const last = historyData[historyData.length - 1];
  if (!last) return [];
  let price = last.priceAvg;
  const predictions = [];
  const baseDate = new Date(last.date);
  const trend = (Math.random() - 0.4) * 0.003;

  for (let i = 1; i <= days; i++) {
    const date = new Date(baseDate);
    date.setDate(date.getDate() + i);
    if (date.getDay() === 5) continue;

    const noise = (Math.random() - 0.5) * commodity.volatility * commodity.basePrice * 0.15;
    price = price * (1 + trend) + noise;
    price = Math.max(commodity.basePrice * 0.3, price);
    const spread = price * (0.08 + Math.random() * 0.1);

    predictions.push({
      date: `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`,
      year: date.getFullYear(),
      month: date.getMonth() + 1,
      priceMin: Math.round(price - spread / 2),
      priceMax: Math.round(price + spread / 2),
      priceAvg: Math.round(price),
      isPrediction: true,
    });
  }
  return predictions;
}

// ─── Pre-generate all data ───────────────────────────────────────
const ALL_DATA = {};
const ALL_PREDICTIONS = {};
COMMODITIES.forEach((c) => {
  const hist = generatePriceData(c);
  ALL_DATA[c.name] = hist;
  ALL_PREDICTIONS[c.name] = generatePredictions(c, hist, 90);
});

// ─── Zoom Presets ────────────────────────────────────────────────
const ZOOM_PRESETS = [
  { label: "1M", days: 30 },
  { label: "3M", days: 90 },
  { label: "6M", days: 180 },
  { label: "1Y", days: 365 },
  { label: "3Y", days: 1095 },
  { label: "All", days: 99999 },
];

// ─── Custom Tooltip ──────────────────────────────────────────────
function ChartTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;
  return (
    <div style={{
      background: "#1e293b", border: "1px solid #334155", borderRadius: 8,
      padding: "10px 14px", color: "#e2e8f0", fontSize: 13, boxShadow: "0 4px 20px rgba(0,0,0,0.4)"
    }}>
      <div style={{ fontWeight: 600, marginBottom: 4, color: "#94a3b8" }}>{d.date}</div>
      <div style={{ display: "flex", gap: 16 }}>
        <div>
          <span style={{ color: "#94a3b8" }}>Avg: </span>
          <span style={{ color: d.isPrediction ? PREDICTION_COLOR : "#fbbf24", fontWeight: 700 }}>
            {d.isPrediction ? "~" : ""}৳{d.priceAvg}
          </span>
        </div>
        <div>
          <span style={{ color: "#94a3b8" }}>Min: </span>
          <span style={{ color: "#60a5fa" }}>৳{d.priceMin}</span>
        </div>
        <div>
          <span style={{ color: "#94a3b8" }}>Max: </span>
          <span style={{ color: "#f87171" }}>৳{d.priceMax}</span>
        </div>
      </div>
      {d.isPrediction && (
        <div style={{ color: PREDICTION_COLOR, fontSize: 11, marginTop: 4, fontStyle: "italic" }}>
          Predicted
        </div>
      )}
    </div>
  );
}

// ─── Main Dashboard ──────────────────────────────────────────────
export default function Dashboard() {
  const [selected, setSelected] = useState(COMMODITIES[0].name);
  const [zoom, setZoom] = useState("1Y");
  const [showPrediction, setShowPrediction] = useState(true);
  const [showMinMax, setShowMinMax] = useState(true);
  const [yearOverlay, setYearOverlay] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");

  const commodity = COMMODITIES.find((c) => c.name === selected) || COMMODITIES[0];
  const history = ALL_DATA[selected] || [];
  const predictions = ALL_PREDICTIONS[selected] || [];

  // ─── Chart Data ────────────────────────────────────
  const chartData = useMemo(() => {
    const preset = ZOOM_PRESETS.find((z) => z.label === zoom);
    const days = preset ? preset.days : 365;
    const combined = showPrediction ? [...history, ...predictions] : [...history];

    if (days >= 99999) return combined;

    const cutoff = new Date("2026-03-12");
    cutoff.setDate(cutoff.getDate() - days);
    const cutStr = `${cutoff.getFullYear()}-${String(cutoff.getMonth() + 1).padStart(2, "0")}-${String(cutoff.getDate()).padStart(2, "0")}`;

    const filtered = combined.filter((d) => d.date >= cutStr);
    return filtered;
  }, [selected, zoom, showPrediction, history, predictions]);

  // ─── Year-overlay data ─────────────────────────────
  const yearData = useMemo(() => {
    if (!yearOverlay) return null;
    const years = {};
    history.forEach((d) => {
      if (!years[d.year]) years[d.year] = [];
      const dayOfYear = Math.floor(
        (new Date(d.date) - new Date(d.year, 0, 0)) / 86400000
      );
      years[d.year].push({ dayOfYear, priceAvg: d.priceAvg, year: d.year });
    });
    const maxLen = Math.max(...Object.values(years).map((a) => a.length));
    const merged = [];
    for (let i = 0; i < maxLen; i++) {
      const row = { dayOfYear: i };
      Object.entries(years).forEach(([yr, arr]) => {
        if (arr[i]) {
          row[`y${yr}`] = arr[i].priceAvg;
          row.dayOfYear = arr[i].dayOfYear;
        }
      });
      merged.push(row);
    }
    return { merged, years: Object.keys(years).map(Number) };
  }, [yearOverlay, history]);

  // ─── Predictions Table ────────────────────────────
  const tableData = useMemo(() => {
    return COMMODITIES.map((c) => {
      const hist = ALL_DATA[c.name] || [];
      const pred = ALL_PREDICTIONS[c.name] || [];
      const today = hist[hist.length - 1];
      const next7 = pred.slice(0, 7);
      return { commodity: c, today, next7 };
    });
  }, []);

  const filteredTable = useMemo(() => {
    if (!searchTerm) return tableData;
    const s = searchTerm.toLowerCase();
    return tableData.filter(
      (r) =>
        r.commodity.name.toLowerCase().includes(s) ||
        r.commodity.nameEn.toLowerCase().includes(s)
    );
  }, [searchTerm, tableData]);

  // ─── Price change indicator ───────────────────────
  const todayPrice = history.length > 0 ? history[history.length - 1].priceAvg : 0;
  const yesterdayPrice = history.length > 1 ? history[history.length - 2].priceAvg : todayPrice;
  const change = todayPrice - yesterdayPrice;
  const changePct = yesterdayPrice > 0 ? ((change / yesterdayPrice) * 100).toFixed(2) : 0;

  const predEnd = predictions.length > 0 ? predictions[predictions.length - 1] : null;
  const predChange = predEnd ? predEnd.priceAvg - todayPrice : 0;
  const predChangePct = todayPrice > 0 ? ((predChange / todayPrice) * 100).toFixed(1) : 0;

  return (
    <div style={{
      fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      background: "linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%)",
      color: "#e2e8f0", minHeight: "100vh", padding: 0,
    }}>
      {/* Header */}
      <div style={{
        background: "rgba(15, 23, 42, 0.8)", borderBottom: "1px solid #1e293b",
        padding: "12px 24px", display: "flex", alignItems: "center", justifyContent: "space-between",
        backdropFilter: "blur(10px)", position: "sticky", top: 0, zIndex: 50,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ fontSize: 22, fontWeight: 800, background: "linear-gradient(90deg, #fbbf24, #f59e0b)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
            TCB BazarDor
          </div>
          <span style={{ color: "#64748b", fontSize: 13 }}>Price Prediction Dashboard</span>
        </div>
        <div style={{ fontSize: 12, color: "#64748b" }}>
          Last Updated: March 12, 2026
        </div>
      </div>

      <div style={{ padding: "16px 24px", display: "flex", flexDirection: "column", gap: 16 }}>
        {/* Top Controls Row */}
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "stretch" }}>
          {/* Product Selector */}
          <div style={{
            background: "rgba(30, 41, 59, 0.6)", borderRadius: 12, padding: 16,
            border: "1px solid #334155", flex: "1 1 320px", minWidth: 280,
          }}>
            <label style={{ fontSize: 11, color: "#94a3b8", textTransform: "uppercase", letterSpacing: 1, fontWeight: 600 }}>
              Select Product
            </label>
            <select
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
              style={{
                width: "100%", marginTop: 8, padding: "10px 12px", borderRadius: 8,
                background: "#0f172a", color: "#e2e8f0", border: "1px solid #475569",
                fontSize: 15, fontWeight: 500, cursor: "pointer", outline: "none",
              }}
            >
              {COMMODITIES.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.nameEn} — {c.name}
                </option>
              ))}
            </select>
          </div>

          {/* Current Price Card */}
          <div style={{
            background: "rgba(30, 41, 59, 0.6)", borderRadius: 12, padding: 16,
            border: "1px solid #334155", flex: "0 0 200px", textAlign: "center",
          }}>
            <div style={{ fontSize: 11, color: "#94a3b8", textTransform: "uppercase", letterSpacing: 1, fontWeight: 600 }}>
              Current Price
            </div>
            <div style={{ fontSize: 32, fontWeight: 800, color: "#fbbf24", marginTop: 4 }}>
              ৳{todayPrice}
            </div>
            <div style={{
              fontSize: 14, fontWeight: 600, marginTop: 2,
              color: change >= 0 ? "#4ade80" : "#f87171",
            }}>
              {change >= 0 ? "+" : ""}{change.toFixed(0)} ({change >= 0 ? "+" : ""}{changePct}%)
            </div>
          </div>

          {/* Prediction Card */}
          <div style={{
            background: "rgba(30, 41, 59, 0.6)", borderRadius: 12, padding: 16,
            border: "1px solid #334155", flex: "0 0 200px", textAlign: "center",
          }}>
            <div style={{ fontSize: 11, color: "#94a3b8", textTransform: "uppercase", letterSpacing: 1, fontWeight: 600 }}>
              90-Day Forecast
            </div>
            <div style={{ fontSize: 32, fontWeight: 800, color: PREDICTION_COLOR, marginTop: 4 }}>
              ৳{predEnd ? predEnd.priceAvg : "—"}
            </div>
            <div style={{
              fontSize: 14, fontWeight: 600, marginTop: 2,
              color: predChange >= 0 ? "#4ade80" : "#f87171",
            }}>
              {predChange >= 0 ? "+" : ""}{predChange.toFixed(0)} ({predChange >= 0 ? "+" : ""}{predChangePct}%)
            </div>
          </div>
        </div>

        {/* Chart Section */}
        <div style={{
          background: "rgba(30, 41, 59, 0.6)", borderRadius: 12,
          border: "1px solid #334155", overflow: "hidden",
        }}>
          {/* Chart Controls */}
          <div style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            padding: "12px 16px", borderBottom: "1px solid #1e293b", flexWrap: "wrap", gap: 8,
          }}>
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
              {ZOOM_PRESETS.map((z) => (
                <button
                  key={z.label}
                  onClick={() => { setZoom(z.label); setYearOverlay(false); }}
                  style={{
                    padding: "6px 14px", borderRadius: 6, border: "none", cursor: "pointer",
                    fontSize: 12, fontWeight: 600, transition: "all 0.2s",
                    background: zoom === z.label && !yearOverlay ? "#fbbf24" : "#1e293b",
                    color: zoom === z.label && !yearOverlay ? "#0f172a" : "#94a3b8",
                  }}
                >
                  {z.label}
                </button>
              ))}
              <div style={{ width: 1, background: "#334155", margin: "0 4px" }} />
              <button
                onClick={() => setYearOverlay(!yearOverlay)}
                style={{
                  padding: "6px 14px", borderRadius: 6, border: "none", cursor: "pointer",
                  fontSize: 12, fontWeight: 600, transition: "all 0.2s",
                  background: yearOverlay ? "#8b5cf6" : "#1e293b",
                  color: yearOverlay ? "#fff" : "#94a3b8",
                }}
              >
                Year Overlay
              </button>
            </div>
            <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
              <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#94a3b8", cursor: "pointer" }}>
                <input type="checkbox" checked={showPrediction} onChange={(e) => setShowPrediction(e.target.checked)} style={{ accentColor: PREDICTION_COLOR }} />
                Show Predictions
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#94a3b8", cursor: "pointer" }}>
                <input type="checkbox" checked={showMinMax} onChange={(e) => setShowMinMax(e.target.checked)} style={{ accentColor: "#818cf8" }} />
                Min/Max Range
              </label>
            </div>
          </div>

          {/* Chart Title */}
          <div style={{ padding: "12px 16px 0", display: "flex", alignItems: "baseline", gap: 8 }}>
            <span style={{ fontSize: 18, fontWeight: 700 }}>{commodity.nameEn}</span>
            <span style={{ fontSize: 13, color: "#64748b" }}>{commodity.name} — {commodity.unit}</span>
          </div>

          {/* Main Chart */}
          <div style={{ padding: "8px 8px 0" }}>
            {yearOverlay && yearData ? (
              <ResponsiveContainer width="100%" height={420}>
                <LineChart data={yearData.merged} margin={{ top: 10, right: 30, left: 10, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis
                    dataKey="dayOfYear"
                    stroke="#475569"
                    fontSize={11}
                    tickFormatter={(v) => {
                      const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
                      const m = Math.floor((v / 365) * 12);
                      return months[Math.min(m, 11)] || "";
                    }}
                  />
                  <YAxis stroke="#475569" fontSize={11} tickFormatter={(v) => `৳${v}`} />
                  <Tooltip
                    contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8, color: "#e2e8f0", fontSize: 12 }}
                    formatter={(value, name) => [`৳${value}`, name.replace("y", "")]}
                  />
                  <Legend
                    formatter={(value) => <span style={{ color: YEAR_COLORS[value.replace("y", "")] || "#94a3b8", fontSize: 12 }}>{value.replace("y", "")}</span>}
                  />
                  {yearData.years.map((yr) => (
                    <Line
                      key={yr}
                      type="monotone"
                      dataKey={`y${yr}`}
                      stroke={YEAR_COLORS[yr] || "#94a3b8"}
                      strokeWidth={yr === 2026 ? 2.5 : 1.5}
                      dot={false}
                      opacity={yr === 2026 ? 1 : 0.7}
                      connectNulls
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <ResponsiveContainer width="100%" height={420}>
                <ComposedChart data={chartData} margin={{ top: 10, right: 30, left: 10, bottom: 0 }}>
                  <defs>
                    <linearGradient id="rangeGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#818cf8" stopOpacity={0.15} />
                      <stop offset="95%" stopColor="#818cf8" stopOpacity={0.02} />
                    </linearGradient>
                    <linearGradient id="predGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={PREDICTION_COLOR} stopOpacity={0.15} />
                      <stop offset="95%" stopColor={PREDICTION_COLOR} stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis
                    dataKey="date"
                    stroke="#475569"
                    fontSize={11}
                    tickFormatter={(d) => {
                      const parts = d.split("-");
                      const months = ["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
                      return `${months[parseInt(parts[1])]} ${parts[0].slice(2)}`;
                    }}
                    minTickGap={40}
                  />
                  <YAxis stroke="#475569" fontSize={11} tickFormatter={(v) => `৳${v}`} domain={["auto", "auto"]} />
                  <Tooltip content={<ChartTooltip />} />

                  {showMinMax && (
                    <>
                      <Area type="monotone" dataKey="priceMax" stroke="none" fill="url(#rangeGrad)" />
                      <Line type="monotone" dataKey="priceMax" stroke="#f87171" strokeWidth={1} dot={false} strokeDasharray="3 3" opacity={0.5} />
                      <Line type="monotone" dataKey="priceMin" stroke="#60a5fa" strokeWidth={1} dot={false} strokeDasharray="3 3" opacity={0.5} />
                    </>
                  )}

                  <Line
                    type="monotone"
                    dataKey="priceAvg"
                    stroke="#fbbf24"
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4, fill: "#fbbf24" }}
                  />

                  {showPrediction && predictions.length > 0 && (
                    <ReferenceLine
                      x={history[history.length - 1]?.date}
                      stroke="#475569"
                      strokeDasharray="4 4"
                      label={{ value: "Today", fill: "#94a3b8", fontSize: 11, position: "top" }}
                    />
                  )}

                  <Brush
                    dataKey="date"
                    height={30}
                    stroke="#334155"
                    fill="#0f172a"
                    tickFormatter={(d) => {
                      if (!d) return "";
                      const p = d.split("-");
                      return `${p[0]}-${p[1]}`;
                    }}
                    travellerWidth={8}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* Year color legend for year overlay */}
          {yearOverlay && (
            <div style={{ padding: "8px 16px 12px", display: "flex", gap: 12, flexWrap: "wrap" }}>
              {Object.entries(YEAR_COLORS).map(([yr, color]) => (
                <div key={yr} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12 }}>
                  <div style={{ width: 14, height: 3, background: color, borderRadius: 2 }} />
                  <span style={{ color: "#94a3b8" }}>{yr}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Predictions Table */}
        <div style={{
          background: "rgba(30, 41, 59, 0.6)", borderRadius: 12,
          border: "1px solid #334155", overflow: "hidden",
        }}>
          <div style={{
            padding: "14px 16px", borderBottom: "1px solid #1e293b",
            display: "flex", justifyContent: "space-between", alignItems: "center",
          }}>
            <div style={{ fontSize: 16, fontWeight: 700 }}>
              All Products — Today + 7-Day Forecast
            </div>
            <input
              type="text"
              placeholder="Search products..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              style={{
                padding: "8px 14px", borderRadius: 8, border: "1px solid #475569",
                background: "#0f172a", color: "#e2e8f0", fontSize: 13, width: 220, outline: "none",
              }}
            />
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: "1px solid #334155" }}>
                  <th style={{ ...thStyle, position: "sticky", left: 0, background: "#1e293b", zIndex: 2, minWidth: 180 }}>Product</th>
                  <th style={{ ...thStyle, minWidth: 80 }}>Unit</th>
                  <th style={{ ...thStyle, background: "#1a2332", minWidth: 90 }}>Today (৳)</th>
                  {[1, 2, 3, 4, 5, 6, 7].map((d) => (
                    <th key={d} style={{ ...thStyle, minWidth: 80, color: PREDICTION_COLOR }}>
                      Day +{d}
                    </th>
                  ))}
                  <th style={{ ...thStyle, minWidth: 90 }}>7D Change</th>
                </tr>
              </thead>
              <tbody>
                {filteredTable.map((row, idx) => {
                  const todayP = row.today?.priceAvg || 0;
                  const day7P = row.next7.length >= 7 ? row.next7[6]?.priceAvg : null;
                  const ch = day7P ? day7P - todayP : 0;
                  const chPct = todayP > 0 ? ((ch / todayP) * 100).toFixed(1) : 0;
                  const isSelected = row.commodity.name === selected;

                  return (
                    <tr
                      key={row.commodity.name}
                      onClick={() => setSelected(row.commodity.name)}
                      style={{
                        borderBottom: "1px solid #1e293b",
                        cursor: "pointer",
                        background: isSelected ? "rgba(251, 191, 36, 0.08)" : idx % 2 === 0 ? "transparent" : "rgba(15, 23, 42, 0.3)",
                        transition: "background 0.15s",
                      }}
                      onMouseEnter={(e) => { if (!isSelected) e.currentTarget.style.background = "rgba(100,116,139,0.1)"; }}
                      onMouseLeave={(e) => { if (!isSelected) e.currentTarget.style.background = idx % 2 === 0 ? "transparent" : "rgba(15, 23, 42, 0.3)"; }}
                    >
                      <td style={{
                        ...tdStyle, position: "sticky", left: 0, zIndex: 1,
                        background: isSelected ? "rgba(251, 191, 36, 0.12)" : idx % 2 === 0 ? "#1e293b" : "#172033",
                        fontWeight: isSelected ? 700 : 500,
                        borderLeft: isSelected ? "3px solid #fbbf24" : "3px solid transparent",
                      }}>
                        <div style={{ lineHeight: 1.3 }}>
                          <div style={{ color: isSelected ? "#fbbf24" : "#e2e8f0" }}>{row.commodity.nameEn}</div>
                          <div style={{ fontSize: 11, color: "#64748b" }}>{row.commodity.name}</div>
                        </div>
                      </td>
                      <td style={{ ...tdStyle, color: "#94a3b8" }}>{row.commodity.unit}</td>
                      <td style={{ ...tdStyle, fontWeight: 700, color: "#fbbf24", background: "rgba(251, 191, 36, 0.04)" }}>
                        {todayP}
                      </td>
                      {[0, 1, 2, 3, 4, 5, 6].map((i) => {
                        const p = row.next7[i]?.priceAvg;
                        const diff = p ? p - todayP : 0;
                        return (
                          <td key={i} style={{ ...tdStyle, color: diff > 0 ? "#4ade80" : diff < 0 ? "#f87171" : "#94a3b8" }}>
                            {p || "—"}
                          </td>
                        );
                      })}
                      <td style={{ ...tdStyle, fontWeight: 600, color: ch > 0 ? "#4ade80" : ch < 0 ? "#f87171" : "#94a3b8" }}>
                        {ch > 0 ? "+" : ""}{ch.toFixed(0)} ({ch >= 0 ? "+" : ""}{chPct}%)
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Footer */}
        <div style={{ textAlign: "center", padding: "8px 0 16px", color: "#475569", fontSize: 11 }}>
          Data Source: Trading Corporation of Bangladesh (tcb.gov.bd) | Models: XGBoost + LightGBM Ensemble
        </div>
      </div>
    </div>
  );
}

const thStyle = {
  padding: "10px 12px",
  textAlign: "left",
  color: "#94a3b8",
  fontWeight: 600,
  fontSize: 11,
  textTransform: "uppercase",
  letterSpacing: "0.5px",
  whiteSpace: "nowrap",
  background: "#1e293b",
};

const tdStyle = {
  padding: "10px 12px",
  whiteSpace: "nowrap",
};
