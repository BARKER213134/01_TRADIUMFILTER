import { useState, useEffect, useCallback } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import axios from "axios";
import { Toaster, toast } from "sonner";
import { 
  ChartLine, 
  Gear, 
  TrendUp, 
  TrendDown, 
  CheckCircle, 
  XCircle, 
  Clock,
  Lightning,
  Robot,
  ArrowRight
} from "@phosphor-icons/react";
import { 
  LineChart, 
  Line, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  BarChart,
  Bar,
  Legend
} from "recharts";

// Components
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Status Badge Component
const StatusBadge = ({ status }) => {
  const styles = {
    accepted: "bg-emerald-50 text-emerald-700 border border-emerald-200",
    rejected: "bg-red-50 text-red-700 border border-red-200",
    analyzing: "bg-blue-50 text-blue-700 border border-blue-200",
    pending: "bg-gray-100 text-gray-700 border border-gray-200"
  };
  
  return (
    <span 
      data-testid={`status-badge-${status}`}
      className={`uppercase tracking-widest text-[10px] px-2 py-1 rounded-sm font-bold ${styles[status] || styles.pending}`}
    >
      {status}
    </span>
  );
};

// KPI Card Component
const KPICard = ({ title, value, icon: Icon, trend, color = "default" }) => {
  const colorStyles = {
    default: "text-slate-900",
    success: "text-emerald-600",
    danger: "text-red-600",
    info: "text-blue-600"
  };
  
  return (
    <Card className="bg-white border border-gray-200 rounded-sm" data-testid={`kpi-${title.toLowerCase().replace(/\s/g, '-')}`}>
      <CardContent className="p-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs tracking-widest uppercase text-gray-500 font-bold mb-1">{title}</p>
            <p className={`font-mono text-3xl font-bold tracking-tight ${colorStyles[color]}`}>{value}</p>
          </div>
          {Icon && <Icon size={32} weight="regular" className="text-gray-400" />}
        </div>
        {trend && (
          <p className="text-xs text-gray-500 mt-2 font-medium">{trend}</p>
        )}
      </CardContent>
    </Card>
  );
};

// Dashboard Page
const Dashboard = () => {
  const [stats, setStats] = useState(null);
  const [signals, setSignals] = useState([]);
  const [chartData, setChartData] = useState([]);
  const [botStatus, setBotStatus] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [manualSignal, setManualSignal] = useState("");
  const [isAnalyzing, setIsAnalyzing] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [statsRes, signalsRes, chartRes, statusRes] = await Promise.all([
        axios.get(`${API}/signals/stats`),
        axios.get(`${API}/signals?limit=20`),
        axios.get(`${API}/signals/chart/daily?days=7`),
        axios.get(`${API}/bot/status`)
      ]);
      
      setStats(statsRes.data);
      setSignals(signalsRes.data);
      setChartData(chartRes.data);
      setBotStatus(statusRes.data);
    } catch (error) {
      console.error("Error fetching data:", error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleAnalyzeSignal = async () => {
    if (!manualSignal.trim()) {
      toast.error("Enter a signal to analyze");
      return;
    }
    
    setIsAnalyzing(true);
    try {
      const response = await axios.post(`${API}/signals/analyze`, {
        text: manualSignal
      });
      
      toast.success(`Signal ${response.data.status}: ${response.data.symbol}`);
      setManualSignal("");
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to analyze signal");
    } finally {
      setIsAnalyzing(false);
    }
  };

  const toggleBot = async () => {
    try {
      if (botStatus?.is_running) {
        await axios.post(`${API}/bot/stop`);
        toast.info("Bot stopped");
      } else {
        await axios.post(`${API}/bot/start`);
        toast.success("Bot started");
      }
      fetchData();
    } catch (error) {
      toast.error("Failed to toggle bot");
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-50">
        <div className="text-center">
          <div className="w-8 h-1 bg-slate-900 mb-2 mx-auto animate-pulse"></div>
          <p className="text-xs tracking-widest uppercase text-gray-500 font-bold">Loading</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50" data-testid="dashboard">
      {/* Header */}
      <header className="bg-white/80 backdrop-blur-xl border-b border-gray-200 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Robot size={28} weight="bold" className="text-slate-900" />
              <h1 className="font-sans text-xl font-bold text-slate-900 tracking-tight" style={{ fontFamily: 'Chivo, sans-serif' }}>
                AI Signal Screener
              </h1>
            </div>
            <nav className="flex items-center gap-6">
              <NavLink 
                to="/" 
                className={({ isActive }) => 
                  `text-sm font-medium transition-colors ${isActive ? 'text-slate-900' : 'text-gray-500 hover:text-slate-900'}`
                }
                data-testid="nav-dashboard"
              >
                <ChartLine size={18} weight="regular" className="inline mr-2" />
                Dashboard
              </NavLink>
              <NavLink 
                to="/settings" 
                className={({ isActive }) => 
                  `text-sm font-medium transition-colors ${isActive ? 'text-slate-900' : 'text-gray-500 hover:text-slate-900'}`
                }
                data-testid="nav-settings"
              >
                <Gear size={18} weight="regular" className="inline mr-2" />
                Settings
              </NavLink>
              <div className="flex items-center gap-2 ml-4 pl-4 border-l border-gray-200">
                <div className={`w-2 h-2 rounded-full ${botStatus?.is_running ? 'bg-emerald-500' : 'bg-gray-300'}`}></div>
                <span className="text-xs font-medium text-gray-600">
                  {botStatus?.is_running ? 'Online' : 'Offline'}
                </span>
                <Switch
                  data-testid="bot-toggle"
                  checked={botStatus?.is_running}
                  onCheckedChange={toggleBot}
                />
              </div>
            </nav>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto p-6">
        {/* KPI Row */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-6">
          <KPICard 
            title="Total Signals" 
            value={stats?.total_signals || 0} 
            icon={Lightning}
            trend={`${stats?.today?.total || 0} today`}
          />
          <KPICard 
            title="Accepted" 
            value={stats?.accepted || 0} 
            icon={CheckCircle}
            color="success"
            trend={`${stats?.today?.accepted || 0} today`}
          />
          <KPICard 
            title="Rejected" 
            value={stats?.rejected || 0} 
            icon={XCircle}
            color="danger"
            trend={`${stats?.today?.rejected || 0} today`}
          />
          <KPICard 
            title="Avg R:R" 
            value={stats?.avg_rr_ratio?.toFixed(2) || "0.00"} 
            icon={TrendUp}
            color="info"
            trend={`Win rate: ${stats?.win_rate?.toFixed(1) || 0}%`}
          />
        </div>

        {/* Main Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Chart - 3 cols */}
          <Card className="lg:col-span-3 bg-white border border-gray-200 rounded-sm">
            <CardHeader className="border-b border-gray-100">
              <CardTitle className="text-sm tracking-widest uppercase text-gray-500 font-bold">
                Signal Volume (7 Days)
              </CardTitle>
            </CardHeader>
            <CardContent className="p-6">
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
                  <XAxis 
                    dataKey="date" 
                    tick={{ fontSize: 11, fill: '#6B7280', fontFamily: 'JetBrains Mono' }}
                  />
                  <YAxis 
                    tick={{ fontSize: 11, fill: '#6B7280', fontFamily: 'JetBrains Mono' }}
                  />
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: '#fff', 
                      border: '1px solid #E5E7EB',
                      borderRadius: '2px',
                      fontSize: '12px',
                      fontFamily: 'JetBrains Mono'
                    }}
                  />
                  <Legend />
                  <Bar dataKey="accepted" fill="#059669" name="Accepted" />
                  <Bar dataKey="rejected" fill="#DC2626" name="Rejected" />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Manual Analysis - 1 col */}
          <Card className="bg-white border border-gray-200 rounded-sm">
            <CardHeader className="border-b border-gray-100">
              <CardTitle className="text-sm tracking-widest uppercase text-gray-500 font-bold">
                Manual Analysis
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4">
              <Textarea
                data-testid="manual-signal-input"
                placeholder="Paste signal here...&#10;Example: BUY BTCUSDT @ 95000, TP: 96500, SL: 94200"
                value={manualSignal}
                onChange={(e) => setManualSignal(e.target.value)}
                className="font-mono text-sm border-gray-300 rounded-sm focus:ring-2 focus:ring-slate-900/20 focus:border-slate-900 mb-3 min-h-[100px]"
              />
              <Button 
                data-testid="analyze-button"
                onClick={handleAnalyzeSignal}
                disabled={isAnalyzing}
                className="w-full bg-slate-900 text-white hover:bg-slate-800 rounded-sm font-semibold"
              >
                {isAnalyzing ? (
                  <>
                    <Clock size={16} className="mr-2 animate-spin" />
                    Analyzing...
                  </>
                ) : (
                  <>
                    <Lightning size={16} className="mr-2" />
                    Analyze Signal
                  </>
                )}
              </Button>
            </CardContent>
          </Card>
        </div>

        {/* Signals Table */}
        <Card className="mt-6 bg-white border border-gray-200 rounded-sm overflow-hidden">
          <CardHeader className="border-b border-gray-100">
            <CardTitle className="text-sm tracking-widest uppercase text-gray-500 font-bold">
              Recent Signals
            </CardTitle>
          </CardHeader>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="bg-gray-50">
                  <TableHead className="text-xs tracking-widest uppercase text-gray-500 font-bold">Time</TableHead>
                  <TableHead className="text-xs tracking-widest uppercase text-gray-500 font-bold">Symbol</TableHead>
                  <TableHead className="text-xs tracking-widest uppercase text-gray-500 font-bold">Direction</TableHead>
                  <TableHead className="text-xs tracking-widest uppercase text-gray-500 font-bold">Entry</TableHead>
                  <TableHead className="text-xs tracking-widest uppercase text-gray-500 font-bold">TP</TableHead>
                  <TableHead className="text-xs tracking-widest uppercase text-gray-500 font-bold">SL</TableHead>
                  <TableHead className="text-xs tracking-widest uppercase text-gray-500 font-bold">R:R</TableHead>
                  <TableHead className="text-xs tracking-widest uppercase text-gray-500 font-bold">Status</TableHead>
                  <TableHead className="text-xs tracking-widest uppercase text-gray-500 font-bold">AI Confidence</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {signals.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={9} className="text-center py-8 text-gray-500">
                      No signals yet. Analyze a signal or wait for incoming signals.
                    </TableCell>
                  </TableRow>
                ) : (
                  signals.map((signal) => (
                    <TableRow 
                      key={signal.id} 
                      className="hover:bg-gray-50 transition-colors"
                      data-testid={`signal-row-${signal.id}`}
                    >
                      <TableCell className="font-mono text-sm text-gray-600">
                        {new Date(signal.timestamp).toLocaleTimeString()}
                      </TableCell>
                      <TableCell className="font-mono font-medium text-slate-900">
                        {signal.symbol}
                      </TableCell>
                      <TableCell>
                        <span className={`flex items-center gap-1 font-medium ${
                          signal.direction === 'BUY' ? 'text-emerald-600' : 'text-red-600'
                        }`}>
                          {signal.direction === 'BUY' ? (
                            <TrendUp size={14} weight="bold" />
                          ) : (
                            <TrendDown size={14} weight="bold" />
                          )}
                          {signal.direction}
                        </span>
                      </TableCell>
                      <TableCell className="font-mono text-sm">{signal.entry_price?.toLocaleString()}</TableCell>
                      <TableCell className="font-mono text-sm text-emerald-600">{signal.take_profit?.toLocaleString()}</TableCell>
                      <TableCell className="font-mono text-sm text-red-600">{signal.stop_loss?.toLocaleString()}</TableCell>
                      <TableCell className="font-mono font-medium">{signal.rr_ratio?.toFixed(2)}</TableCell>
                      <TableCell><StatusBadge status={signal.status} /></TableCell>
                      <TableCell className="font-mono text-sm">
                        {signal.ai_analysis?.confidence ? `${signal.ai_analysis.confidence}%` : '-'}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </Card>
      </main>
    </div>
  );
};

// Settings Page
const Settings = () => {
  const [settings, setSettings] = useState({
    telegram_api_id: "",
    telegram_api_hash: "",
    telegram_phone: "",
    source_chat_id: "",
    min_rr_ratio: 2.0,
    min_volume_multiplier: 1.5,
    trend_alignment_required: true,
    send_rejected: false
  });
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const response = await axios.get(`${API}/settings`);
        setSettings(prev => ({ ...prev, ...response.data }));
      } catch (error) {
        console.error("Error fetching settings:", error);
      }
    };
    fetchSettings();
  }, []);

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await axios.post(`${API}/settings`, settings);
      toast.success("Settings saved successfully");
    } catch (error) {
      toast.error("Failed to save settings");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50" data-testid="settings-page">
      {/* Header */}
      <header className="bg-white/80 backdrop-blur-xl border-b border-gray-200 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Robot size={28} weight="bold" className="text-slate-900" />
              <h1 className="font-sans text-xl font-bold text-slate-900 tracking-tight" style={{ fontFamily: 'Chivo, sans-serif' }}>
                AI Signal Screener
              </h1>
            </div>
            <nav className="flex items-center gap-6">
              <NavLink 
                to="/" 
                className={({ isActive }) => 
                  `text-sm font-medium transition-colors ${isActive ? 'text-slate-900' : 'text-gray-500 hover:text-slate-900'}`
                }
                data-testid="nav-dashboard"
              >
                <ChartLine size={18} weight="regular" className="inline mr-2" />
                Dashboard
              </NavLink>
              <NavLink 
                to="/settings" 
                className={({ isActive }) => 
                  `text-sm font-medium transition-colors ${isActive ? 'text-slate-900' : 'text-gray-500 hover:text-slate-900'}`
                }
                data-testid="nav-settings"
              >
                <Gear size={18} weight="regular" className="inline mr-2" />
                Settings
              </NavLink>
            </nav>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-4xl mx-auto p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Telegram Configuration */}
          <Card className="bg-white border border-gray-200 rounded-sm">
            <CardHeader className="border-b border-gray-100">
              <CardTitle className="text-sm tracking-widest uppercase text-gray-500 font-bold">
                Telegram Configuration
              </CardTitle>
            </CardHeader>
            <CardContent className="p-6 space-y-4">
              <p className="text-xs text-gray-500 mb-4">
                To read signals from your private bot, you need Telegram API credentials from{" "}
                <a href="https://my.telegram.org" target="_blank" rel="noopener noreferrer" className="text-blue-600 underline">
                  my.telegram.org
                </a>
              </p>
              
              <div>
                <Label className="text-xs tracking-widest uppercase text-gray-500 font-bold mb-1.5 block">
                  API ID
                </Label>
                <Input
                  data-testid="telegram-api-id"
                  type="text"
                  value={settings.telegram_api_id}
                  onChange={(e) => setSettings({ ...settings, telegram_api_id: e.target.value })}
                  className="font-mono border-gray-300 rounded-sm focus:ring-2 focus:ring-slate-900/20 focus:border-slate-900"
                  placeholder="12345678"
                />
              </div>
              
              <div>
                <Label className="text-xs tracking-widest uppercase text-gray-500 font-bold mb-1.5 block">
                  API Hash
                </Label>
                <Input
                  data-testid="telegram-api-hash"
                  type="password"
                  value={settings.telegram_api_hash}
                  onChange={(e) => setSettings({ ...settings, telegram_api_hash: e.target.value })}
                  className="font-mono border-gray-300 rounded-sm focus:ring-2 focus:ring-slate-900/20 focus:border-slate-900"
                  placeholder="0123456789abcdef"
                />
              </div>
              
              <div>
                <Label className="text-xs tracking-widest uppercase text-gray-500 font-bold mb-1.5 block">
                  Phone Number
                </Label>
                <Input
                  data-testid="telegram-phone"
                  type="text"
                  value={settings.telegram_phone}
                  onChange={(e) => setSettings({ ...settings, telegram_phone: e.target.value })}
                  className="font-mono border-gray-300 rounded-sm focus:ring-2 focus:ring-slate-900/20 focus:border-slate-900"
                  placeholder="+79991234567"
                />
              </div>
              
              <div>
                <Label className="text-xs tracking-widest uppercase text-gray-500 font-bold mb-1.5 block">
                  Source Chat ID
                </Label>
                <Input
                  data-testid="source-chat-id"
                  type="text"
                  value={settings.source_chat_id}
                  onChange={(e) => setSettings({ ...settings, source_chat_id: e.target.value })}
                  className="font-mono border-gray-300 rounded-sm focus:ring-2 focus:ring-slate-900/20 focus:border-slate-900"
                  placeholder="Chat ID to read signals from"
                />
              </div>
            </CardContent>
          </Card>

          {/* AI Filter Rules */}
          <Card className="bg-white border border-gray-200 rounded-sm">
            <CardHeader className="border-b border-gray-100">
              <CardTitle className="text-sm tracking-widest uppercase text-gray-500 font-bold">
                AI Filter Rules
              </CardTitle>
            </CardHeader>
            <CardContent className="p-6 space-y-4">
              <div>
                <Label className="text-xs tracking-widest uppercase text-gray-500 font-bold mb-1.5 block">
                  Minimum R:R Ratio
                </Label>
                <Input
                  data-testid="min-rr-ratio"
                  type="number"
                  step="0.1"
                  min="0.5"
                  value={settings.min_rr_ratio}
                  onChange={(e) => setSettings({ ...settings, min_rr_ratio: parseFloat(e.target.value) })}
                  className="font-mono border-gray-300 rounded-sm focus:ring-2 focus:ring-slate-900/20 focus:border-slate-900"
                />
                <p className="text-xs text-gray-400 mt-1">Signals with lower R:R will be rejected</p>
              </div>
              
              <div>
                <Label className="text-xs tracking-widest uppercase text-gray-500 font-bold mb-1.5 block">
                  Minimum Volume Multiplier
                </Label>
                <Input
                  data-testid="min-volume"
                  type="number"
                  step="0.1"
                  min="0.5"
                  value={settings.min_volume_multiplier}
                  onChange={(e) => setSettings({ ...settings, min_volume_multiplier: parseFloat(e.target.value) })}
                  className="font-mono border-gray-300 rounded-sm focus:ring-2 focus:ring-slate-900/20 focus:border-slate-900"
                />
                <p className="text-xs text-gray-400 mt-1">Volume must be N times above average</p>
              </div>
              
              <div className="flex items-center justify-between py-3 border-t border-gray-100">
                <div>
                  <Label className="text-sm font-medium text-slate-900">Trend Alignment Required</Label>
                  <p className="text-xs text-gray-400">Signal direction must match overall trend</p>
                </div>
                <Switch
                  data-testid="trend-alignment"
                  checked={settings.trend_alignment_required}
                  onCheckedChange={(checked) => setSettings({ ...settings, trend_alignment_required: checked })}
                />
              </div>
              
              <div className="flex items-center justify-between py-3 border-t border-gray-100">
                <div>
                  <Label className="text-sm font-medium text-slate-900">Send Rejected Signals</Label>
                  <p className="text-xs text-gray-400">Also forward rejected signals with reasoning</p>
                </div>
                <Switch
                  data-testid="send-rejected"
                  checked={settings.send_rejected}
                  onCheckedChange={(checked) => setSettings({ ...settings, send_rejected: checked })}
                />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Save Button */}
        <div className="mt-6 flex justify-end">
          <Button
            data-testid="save-settings"
            onClick={handleSave}
            disabled={isSaving}
            className="bg-slate-900 text-white hover:bg-slate-800 rounded-sm px-8 font-semibold"
          >
            {isSaving ? "Saving..." : "Save Settings"}
            <ArrowRight size={16} className="ml-2" />
          </Button>
        </div>

        {/* Info Card */}
        <Card className="mt-6 bg-blue-50 border border-blue-200 rounded-sm">
          <CardContent className="p-6">
            <h3 className="font-semibold text-blue-900 mb-2">How it works</h3>
            <ol className="text-sm text-blue-800 space-y-2 list-decimal list-inside">
              <li>Configure your Telegram API credentials from my.telegram.org</li>
              <li>Set the source chat ID (your signal bot's chat)</li>
              <li>Configure filter rules (R:R ratio, volume, trend alignment)</li>
              <li>Start the bot to begin monitoring signals</li>
              <li>AI analyzes each signal using Binance market data and GPT-5.2</li>
              <li>Filtered signals are sent to your destination chat</li>
            </ol>
          </CardContent>
        </Card>
      </main>
    </div>
  );
};

function App() {
  return (
    <div className="App font-sans" style={{ fontFamily: "'IBM Plex Sans', sans-serif" }}>
      <Toaster position="top-right" richColors />
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;
