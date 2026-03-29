import { useState, useEffect, useCallback } from "react";
import "@/App.css";
import axios from "axios";
import { Toaster, toast } from "sonner";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

function App() {
  const [tab, setTab] = useState("tradium");
  const [signals, setSignals] = useState([]);
  const [entries, setEntries] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedSignal, setSelectedSignal] = useState(null);
  const [selected, setSelected] = useState(new Set());

  const fetchData = useCallback(async () => {
    try {
      const [sigRes, entRes, statsRes] = await Promise.all([
        axios.get(`${API}/signals?limit=50`),
        axios.get(`${API}/entries?limit=50`),
        axios.get(`${API}/entries/stats`)
      ]);
      setSignals(sigRes.data);
      setEntries(entRes.data);
      setStats(statsRes.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Clear selection when switching tabs
  useEffect(() => { setSelected(new Set()); }, [tab]);

  const currentItems = (() => {
    if (tab === "tradium") return signals.filter(s => s.status === "watching");
    if (tab === "dca4") return signals.filter(s => s.status === "dca4_reached");
    if (tab === "confirmed") return signals.filter(s => s.status === "entered");
    if (tab === "results") return entries;
    return [];
  })();

  const getItemId = (item) => item.signal_id || item.id;

  const toggleSelect = (id) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (selected.size === currentItems.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(currentItems.map(getItemId)));
    }
  };

  const deleteSelected = async () => {
    if (selected.size === 0) return;
    const ids = [...selected];

    try {
      if (tab === "results") {
        await axios.post(`${API}/entries/delete-batch`, { ids });
      } else {
        await axios.post(`${API}/signals/delete-batch`, { ids });
      }
      toast.success(`Удалено: ${ids.length}`);
      setSelected(new Set());
      fetchData();
    } catch (e) {
      toast.error("Ошибка удаления");
    }
  };

  const tradiumSignals = signals.filter(s => s.status === "watching");
  const dca4Signals = signals.filter(s => s.status === "dca4_reached");
  const confirmedSignals = signals.filter(s => s.status === "entered");

  if (loading) {
    return (
      <div className="loader">
        <div className="loader-bar" />
        <p>ЗАГРУЗКА</p>
      </div>
    );
  }

  return (
    <div className="app">
      <Toaster position="top-right" richColors />

      <header className="header">
        <div className="header-inner">
          <h1 className="logo">TRADIUM MONITOR</h1>
          <div className="stats-row">
            <StatPill label="Сигналы" value={stats?.total_signals || 0} />
            <StatPill label="Слежу" value={stats?.watching || 0} color="blue" />
            <StatPill label="DCA#4" value={stats?.dca4_reached || 0} color="purple" />
            <StatPill label="Открыто" value={stats?.open || 0} color="yellow" />
            <StatPill label="TP" value={stats?.tp_hit || 0} color="green" />
            <StatPill label="SL" value={stats?.sl_hit || 0} color="red" />
            <StatPill label="Win" value={`${stats?.win_rate || 0}%`} color={stats?.win_rate >= 50 ? "green" : "red"} />
          </div>
        </div>
      </header>

      <div className="tabs">
        <button data-testid="tab-tradium" className={`tab ${tab === "tradium" ? "active" : ""}`} onClick={() => setTab("tradium")}>
          Tradium<span className="tab-count">{tradiumSignals.length}</span>
        </button>
        <button data-testid="tab-dca4" className={`tab ${tab === "dca4" ? "active" : ""}`} onClick={() => setTab("dca4")}>
          DCA#4<span className="tab-count">{dca4Signals.length}</span>
        </button>
        <button data-testid="tab-confirmed" className={`tab ${tab === "confirmed" ? "active" : ""}`} onClick={() => setTab("confirmed")}>
          Вход + Разворот<span className="tab-count">{confirmedSignals.length}</span>
        </button>
        <button data-testid="tab-results" className={`tab ${tab === "results" ? "active" : ""}`} onClick={() => setTab("results")}>
          Результаты<span className="tab-count">{entries.length}</span>
        </button>
      </div>

      {currentItems.length > 0 && (
        <div className="bulk-actions" data-testid="bulk-actions">
          <label className="select-all-label" data-testid="select-all">
            <input
              type="checkbox"
              checked={selected.size === currentItems.length && currentItems.length > 0}
              onChange={toggleAll}
            />
            <span>Выбрать все ({currentItems.length})</span>
          </label>
          {selected.size > 0 && (
            <button className="delete-btn" data-testid="delete-selected-btn" onClick={deleteSelected}>
              Удалить выбранные ({selected.size})
            </button>
          )}
        </div>
      )}

      <main className="content">
        {tab === "tradium" ? (
          <SignalsTable signals={tradiumSignals} onSelect={setSelectedSignal} selected={selected} onToggle={toggleSelect} />
        ) : tab === "dca4" ? (
          <DCA4Table signals={dca4Signals} onSelect={setSelectedSignal} selected={selected} onToggle={toggleSelect} />
        ) : tab === "confirmed" ? (
          <ConfirmedTable signals={confirmedSignals} onSelect={setSelectedSignal} selected={selected} onToggle={toggleSelect} />
        ) : (
          <EntriesTable entries={entries} onSelect={setSelectedSignal} selected={selected} onToggle={toggleSelect} />
        )}
      </main>

      {selectedSignal && (
        <SignalModal signal={selectedSignal} onClose={() => setSelectedSignal(null)} />
      )}
    </div>
  );
}

const StatPill = ({ label, value, color = "default" }) => {
  const cls = {
    default: "pill-default", blue: "pill-blue", green: "pill-green",
    red: "pill-red", yellow: "pill-yellow", purple: "pill-purple"
  };
  return (
    <div className={`stat-pill ${cls[color]}`} data-testid={`stat-${label.toLowerCase()}`}>
      <span className="pill-value">{value}</span>
      <span className="pill-label">{label}</span>
    </div>
  );
};

const SignalModal = ({ signal, onClose }) => {
  const [chartUrl, setChartUrl] = useState(null);
  const [chartLoading, setChartLoading] = useState(true);

  useEffect(() => {
    if (signal.chart_path) {
      const filename = signal.chart_path.split("/").pop();
      setChartUrl(`${API}/charts/${filename}`);
    }
    setChartLoading(false);
  }, [signal]);

  useEffect(() => {
    const handleEsc = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handleEsc);
    return () => document.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  const isShort = signal.direction === "SHORT" || signal.direction === "SELL";
  const time = signal.timestamp ? new Date(signal.timestamp).toLocaleString("ru-RU") : "—";

  const statusCls = { watching: "status-watching", dca4_reached: "status-dca4", entered: "status-entered", tp_hit: "status-tp", sl_hit: "status-sl" };
  const statusText = { watching: "Слежу", dca4_reached: "DCA#4", entered: "Вход", tp_hit: "TP", sl_hit: "SL" };

  return (
    <div className="modal-overlay" data-testid="signal-modal-overlay" onClick={onClose}>
      <div className="modal-content" data-testid="signal-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title-row">
            <span className={`dir ${isShort ? "dir-short" : "dir-long"}`}>{isShort ? "SHORT" : "LONG"}</span>
            <h2 className="modal-symbol">{signal.symbol?.replace("USDT", "")}<span className="modal-pair">/USDT</span></h2>
            <span className="modal-tf">{signal.timeframe || "—"}</span>
            <span className={`status ${statusCls[signal.status] || ""}`}>{statusText[signal.status] || signal.status}</span>
          </div>
          <button className="modal-close" data-testid="modal-close-btn" onClick={onClose}>✕</button>
        </div>

        {chartLoading ? (
          <div className="modal-chart-loading">Загрузка графика...</div>
        ) : chartUrl ? (
          <div className="modal-chart"><img src={chartUrl} alt={`Chart ${signal.symbol}`} data-testid="signal-chart-img" /></div>
        ) : (
          <div className="modal-no-chart">Нет графика</div>
        )}

        <div className="modal-grid">
          <InfoBlock label="DCA #4" value={signal.dca4_level} accent />
          <InfoBlock label="Entry" value={fmt(signal.entry_price)} />
          <InfoBlock label="Take Profit" value={fmt(signal.take_profit)} color="green" />
          <InfoBlock label="Stop Loss" value={fmt(signal.stop_loss)} color="red" />
          <InfoBlock label="R:R" value={signal.rr_ratio || "—"} />
          <InfoBlock label="Тренд" value={signal.trend || "—"} />
          <InfoBlock label="MA" value={signal.ma_status || "—"} />
          <InfoBlock label="RSI" value={signal.rsi_status || "—"} />
          <InfoBlock label="Volume 1D" value={signal.volume_1d ? `${signal.volume_1d}M` : "—"} />
          <InfoBlock label="TP %" value={signal.tp_pct ? `${signal.tp_pct}%` : "—"} color="green" />
          <InfoBlock label="SL %" value={signal.sl_pct ? `${signal.sl_pct}%` : "—"} color="red" />
          <InfoBlock label="Время" value={time} />
        </div>

        {signal.dca_data && (
          <div className="modal-dca-section">
            <h3 className="modal-section-title">DCA Уровни</h3>
            <div className="modal-dca-grid">
              {[1,2,3,4,5].map(n => (
                <div key={n} className={`dca-item ${n === 4 ? "dca-highlight" : ""}`}>
                  <span className="dca-label">DCA #{n}</span>
                  <span className="dca-value">{signal.dca_data[`dca${n}`] || "—"}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {signal.reversal_pattern && (
          <div className="modal-ai-section">
            <h3 className="modal-section-title">Разворотная свеча</h3>
            <div className="modal-grid" style={{borderBottom: 'none'}}>
              <InfoBlock label="Паттерн" value={signal.reversal_pattern} accent />
              <InfoBlock label="Сила" value={signal.pattern_strength ? `${(signal.pattern_strength * 100).toFixed(0)}%` : "—"} color="green" />
              <InfoBlock label="Цена входа" value={fmt(signal.trigger_price)} />
              <InfoBlock label="Время" value={signal.trigger_time ? new Date(signal.trigger_time).toLocaleString("ru-RU") : "—"} />
            </div>
          </div>
        )}

        {signal.ai_analysis && (
          <div className="modal-ai-section">
            <h3 className="modal-section-title">AI Анализ</h3>
            <p className="modal-ai-text">{signal.ai_analysis.reasoning || JSON.stringify(signal.ai_analysis)}</p>
          </div>
        )}
      </div>
    </div>
  );
};

const InfoBlock = ({ label, value, color, accent }) => (
  <div className={`info-block ${accent ? "info-accent" : ""}`}>
    <span className="info-label">{label}</span>
    <span className={`info-value ${color || ""}`}>{value ?? "—"}</span>
  </div>
);

const CheckCell = ({ id, selected, onToggle }) => (
  <td className="check-cell" onClick={e => e.stopPropagation()}>
    <input type="checkbox" checked={selected.has(id)} onChange={() => onToggle(id)} data-testid={`check-${id}`} />
  </td>
);

const SignalsTable = ({ signals, onSelect, selected, onToggle }) => {
  if (!signals.length) return <div className="empty" data-testid="signals-empty">Нет сигналов из Tradium</div>;

  return (
    <div className="table-wrap" data-testid="signals-table">
      <table>
        <thead>
          <tr>
            <th className="th-check"></th>
            <th>Время</th><th>Пара</th><th>TF</th><th>Направление</th><th>DCA #4</th>
            <th>Entry</th><th>TP</th><th>SL</th><th>R:R</th><th>Тренд</th><th>Статус</th>
          </tr>
        </thead>
        <tbody>
          {signals.map((s, i) => {
            const isShort = s.direction === "SHORT" || s.direction === "SELL";
            const id = s.id;
            const time = s.timestamp ? new Date(s.timestamp).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";
            return (
              <tr key={id || i} data-testid={`signal-row-${i}`} className={`clickable-row ${selected.has(id) ? "row-selected" : ""}`} onClick={() => onSelect(s)}>
                <CheckCell id={id} selected={selected} onToggle={onToggle} />
                <td className="mono dim">{time}</td>
                <td className="mono bold">{s.symbol?.replace("USDT", "")}</td>
                <td className="mono dim">{s.timeframe || "—"}</td>
                <td><span className={`dir ${isShort ? "dir-short" : "dir-long"}`}>{isShort ? "SHORT" : "LONG"}</span></td>
                <td className="mono accent">{s.dca4_level || "—"}</td>
                <td className="mono">{fmt(s.entry_price)}</td>
                <td className="mono green">{fmt(s.take_profit)}</td>
                <td className="mono red">{fmt(s.stop_loss)}</td>
                <td className="mono bold">{s.rr_ratio || "—"}</td>
                <td className="trend-cell">{s.trend || "—"}</td>
                <td><span className="status status-watching">Слежу</span></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

const DCA4Table = ({ signals, onSelect, selected, onToggle }) => {
  if (!signals.length) return <div className="empty" data-testid="dca4-empty">Нет сигналов на уровне DCA #4</div>;

  return (
    <div className="table-wrap" data-testid="dca4-table">
      <table>
        <thead>
          <tr>
            <th className="th-check"></th>
            <th>Достигнут</th><th>Пара</th><th>TF</th><th>Направление</th><th>DCA #4</th>
            <th>Цена</th><th>TP</th><th>SL</th><th>R:R</th><th>Тренд</th>
          </tr>
        </thead>
        <tbody>
          {signals.map((s, i) => {
            const isShort = s.direction === "SHORT" || s.direction === "SELL";
            const id = s.id;
            const time = s.dca4_reached_at ? new Date(s.dca4_reached_at).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";
            return (
              <tr key={id || i} data-testid={`dca4-row-${i}`} className={`clickable-row ${selected.has(id) ? "row-selected" : ""}`} onClick={() => onSelect(s)}>
                <CheckCell id={id} selected={selected} onToggle={onToggle} />
                <td className="mono dim">{time}</td>
                <td className="mono bold">{s.symbol?.replace("USDT", "")}</td>
                <td className="mono dim">{s.timeframe || "—"}</td>
                <td><span className={`dir ${isShort ? "dir-short" : "dir-long"}`}>{isShort ? "SHORT" : "LONG"}</span></td>
                <td className="mono accent">{s.dca4_level || "—"}</td>
                <td className="mono">{fmt(s.dca4_reached_price)}</td>
                <td className="mono green">{fmt(s.take_profit)}</td>
                <td className="mono red">{fmt(s.stop_loss)}</td>
                <td className="mono bold">{s.rr_ratio || "—"}</td>
                <td className="trend-cell">{s.trend || "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

const ConfirmedTable = ({ signals, onSelect, selected, onToggle }) => {
  if (!signals.length) return <div className="empty" data-testid="confirmed-empty">Нет подтверждённых сигналов</div>;

  return (
    <div className="table-wrap" data-testid="confirmed-table">
      <table>
        <thead>
          <tr>
            <th className="th-check"></th>
            <th>Время входа</th><th>Пара</th><th>TF</th><th>Направление</th><th>Паттерн</th>
            <th>Сила</th><th>DCA #4</th><th>Цена входа</th><th>TP</th><th>SL</th><th>R:R</th>
          </tr>
        </thead>
        <tbody>
          {signals.map((s, i) => {
            const isShort = s.direction === "SHORT" || s.direction === "SELL";
            const id = s.id;
            const time = s.trigger_time ? new Date(s.trigger_time).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";
            const strength = s.pattern_strength ? `${(s.pattern_strength * 100).toFixed(0)}%` : "—";
            return (
              <tr key={id || i} data-testid={`confirmed-row-${i}`} className={`clickable-row ${selected.has(id) ? "row-selected" : ""}`} onClick={() => onSelect(s)}>
                <CheckCell id={id} selected={selected} onToggle={onToggle} />
                <td className="mono dim">{time}</td>
                <td className="mono bold">{s.symbol?.replace("USDT", "")}</td>
                <td className="mono dim">{s.timeframe || "—"}</td>
                <td><span className={`dir ${isShort ? "dir-short" : "dir-long"}`}>{isShort ? "SHORT" : "LONG"}</span></td>
                <td className="mono">{s.reversal_pattern || "—"}</td>
                <td className="mono green">{strength}</td>
                <td className="mono accent">{s.dca4_level || "—"}</td>
                <td className="mono">{fmt(s.trigger_price)}</td>
                <td className="mono green">{fmt(s.take_profit)}</td>
                <td className="mono red">{fmt(s.stop_loss)}</td>
                <td className="mono bold">{s.rr_ratio || "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

const EntriesTable = ({ entries, onSelect, selected, onToggle }) => {
  if (!entries.length) return <div className="empty" data-testid="entries-empty">Нет результатов</div>;

  return (
    <div className="table-wrap" data-testid="entries-table">
      <table>
        <thead>
          <tr>
            <th className="th-check"></th>
            <th>Время входа</th><th>Пара</th><th>Тип</th><th>Направление</th><th>Цена входа</th>
            <th>DCA #4</th><th>TP</th><th>SL</th><th>R:R</th><th>P&L</th><th>Статус</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((e, i) => {
            const isShort = e.direction === "SHORT" || e.direction === "SELL";
            const id = e.signal_id;
            const time = e.triggered_at ? new Date(e.triggered_at).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";

            let pnl = "", pnlCls = "";
            if (e.close_price && e.entry_price) {
              const diff = isShort ? ((e.entry_price - e.close_price) / e.entry_price) * 100 : ((e.close_price - e.entry_price) / e.entry_price) * 100;
              pnl = `${diff > 0 ? "+" : ""}${diff.toFixed(2)}%`;
              pnlCls = diff > 0 ? "green" : "red";
            }

            const statusCls = { OPEN: "status-watching", TP_HIT: "status-tp", SL_HIT: "status-sl" };
            const statusText = { OPEN: "Открыта", TP_HIT: "TP", SL_HIT: "SL" };
            const entryType = e.entry_type || "—";
            const typeCls = entryType === "DCA#4" ? "status-dca4" : entryType === "Разворот" ? "status-entered" : "";

            return (
              <tr key={id || i} data-testid={`entry-row-${i}`} className={`clickable-row ${selected.has(id) ? "row-selected" : ""}`} onClick={() => onSelect(e)}>
                <CheckCell id={id} selected={selected} onToggle={onToggle} />
                <td className="mono dim">{time}</td>
                <td className="mono bold">{e.symbol?.replace("USDT", "")}</td>
                <td><span className={`status ${typeCls}`}>{entryType}</span></td>
                <td><span className={`dir ${isShort ? "dir-short" : "dir-long"}`}>{isShort ? "SHORT" : "LONG"}</span></td>
                <td className="mono">{fmt(e.entry_price)}</td>
                <td className="mono accent">{fmt(e.dca4_level)}</td>
                <td className="mono green">{fmt(e.take_profit)}</td>
                <td className="mono red">{fmt(e.stop_loss)}</td>
                <td className="mono bold">{e.rr_ratio || "—"}</td>
                <td className={`mono bold ${pnlCls}`}>{pnl || "—"}</td>
                <td><span className={`status ${statusCls[e.status] || ""}`}>{statusText[e.status] || e.status}</span></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

function fmt(n) {
  if (n == null) return "—";
  if (typeof n === "number") {
    if (n < 0.01) return n.toFixed(6);
    if (n < 1) return n.toFixed(4);
    if (n < 100) return n.toFixed(2);
    return n.toLocaleString("en-US", { maximumFractionDigits: 2 });
  }
  return String(n);
}

export default App;
