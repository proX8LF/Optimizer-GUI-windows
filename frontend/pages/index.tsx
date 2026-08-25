import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

const BACKEND_URL = "http://127.0.0.1:8765";

interface ParamSchema {
  name: string;
  type: "process_select" | "core_multiselect" | "select" | "text" | "number" | "checkbox";
  label: string;
  options?: string[];
}

interface MenuItem {
  id: string;
  label: string;
  params: ParamSchema[];
}

interface MenuCategory {
  id: string;
  title: string;
  items: MenuItem[];
}

interface ProcessInfo {
  pid: string;
  name: string;
}

export default function Dashboard() {
  const [menu, setMenu] = useState<MenuCategory[]>([]);
  const [activeCat, setActiveCat] = useState<string>("");
  const [expandedItem, setExpandedItem] = useState<string | null>(null);
  const [processes, setProcesses] = useState<ProcessInfo[]>([]);
  const [cpuCount, setCpuCount] = useState<number>(8);
  const [isAdmin, setIsAdmin] = useState<boolean>(false);
  const [formValues, setFormValues] = useState<Record<string, any>>({});
  const [log, setLog] = useState<{ text: string; ok: boolean }[]>([]);
  const [connError, setConnError] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const [menuRes, procRes, cpuRes, adminRes] = await Promise.all([
          fetch(`${BACKEND_URL}/api/menu`),
          fetch(`${BACKEND_URL}/api/processes`),
          fetch(`${BACKEND_URL}/api/cpu-count`),
          fetch(`${BACKEND_URL}/api/admin-status`),
        ]);
        const menuData: MenuCategory[] = await menuRes.json();
        setMenu(menuData);
        setActiveCat(menuData[0]?.id ?? "");
        setProcesses(await procRes.json());
        setCpuCount((await cpuRes.json()).count);
        setIsAdmin((await adminRes.json()).is_admin);
        setConnError(false);
      } catch {
        setConnError(true);
      }
    };
    load();
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/api/processes`);
        setProcesses(await res.json());
      } catch {
        /* ignore */
      }
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  const setField = (name: string, value: any) => {
    setFormValues((prev) => ({ ...prev, [name]: value }));
  };

  const toggleCore = (name: string, core: number) => {
    setFormValues((prev) => {
      const current: number[] = prev[name] || [];
      const next = current.includes(core) ? current.filter((c) => c !== core) : [...current, core];
      return { ...prev, [name]: next };
    });
  };

  const runAction = async (categoryId: string, item: MenuItem) => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category: categoryId, item: item.id, params: formValues }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Action failed");
      setLog((prev) => [{ text: data.message, ok: true }, ...prev].slice(0, 8));
    } catch (e: any) {
      setLog((prev) => [{ text: e.message || "Action failed", ok: false }, ...prev].slice(0, 8));
    }
  };

  const activeMenu = menu.find((c) => c.id === activeCat);

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#141417] via-[#0e0e10] to-black text-white flex flex-col">
      {/* Title bar */}
      <div className="glass mx-4 mt-4 rounded-2xl px-5 py-3 flex items-center justify-between shadow-2xl shadow-black/50 select-none">
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-full bg-[#ff5f57]" />
          <span className="w-3 h-3 rounded-full bg-[#febc2e]" />
          <span className="w-3 h-3 rounded-full bg-[#28c840]" />
          <span className="ml-3 font-semibold text-sm text-neutral-200">Optimizer</span>
        </div>
        <div className="flex items-center gap-3 text-xs text-neutral-400">
          <span>{isAdmin ? "Administrator" : "Not elevated - some actions will fail"}</span>
          <span className={`w-2 h-2 rounded-full ${isAdmin ? "bg-emerald-400" : "bg-yellow-400"}`} />
        </div>
      </div>

      {connError && (
        <div className="mx-4 mt-3 rounded-2xl bg-red-500/10 border border-red-500/30 px-4 py-3 text-red-300 text-sm">
          Cannot reach the backend at {BACKEND_URL}. Make sure the Python server is running.
        </div>
      )}

      <div className="flex-1 flex gap-4 p-4 min-h-0">
        {/* Sidebar */}
        <div className="glass w-64 rounded-2xl p-3 overflow-y-auto shrink-0">
          <p className="text-xs uppercase tracking-wider text-neutral-500 px-2 mb-2">Categories</p>
          <div className="flex flex-col gap-1">
            {menu.map((cat) => (
              <button
                key={cat.id}
                onClick={() => { setActiveCat(cat.id); setExpandedItem(null); }}
                className={`text-left px-3 py-2.5 rounded-xl text-sm transition-colors ${
                  activeCat === cat.id ? "bg-blue-500/90 text-white" : "hover:bg-white/10 text-neutral-300"
                }`}
              >
                {cat.title}
              </button>
            ))}
          </div>
        </div>

        {/* Main content */}
        <div className="flex-1 flex flex-col gap-4 min-w-0">
          <div className="glass flex-1 rounded-2xl p-5 overflow-y-auto">
            <h2 className="text-lg font-semibold mb-4">{activeMenu?.title}</h2>
            <div className="flex flex-col gap-2">
              {activeMenu?.items.map((item) => (
                <div key={item.id} className="rounded-xl bg-white/5 border border-white/10 overflow-hidden">
                  <button
                    onClick={() => { setExpandedItem(expandedItem === item.id ? null : item.id); setFormValues({}); }}
                    className="w-full flex items-center justify-between px-4 py-3 text-sm hover:bg-white/5 transition-colors"
                  >
                    <span>{item.label}</span>
                    <span className="text-neutral-500">{expandedItem === item.id ? "\u2212" : "+"}</span>
                  </button>

                  <AnimatePresence>
                    {expandedItem === item.id && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="px-4 pb-4"
                      >
                        <div className="flex flex-col gap-3 pt-1">
                          {item.params.map((p) => (
                            <FieldRenderer
                              key={p.name}
                              schema={p}
                              value={formValues[p.name]}
                              onChange={(v) => setField(p.name, v)}
                              onToggleCore={(c) => toggleCore(p.name, c)}
                              processes={processes}
                              cpuCount={cpuCount}
                            />
                          ))}
                          <button
                            onClick={() => runAction(activeCat, item)}
                            className="self-start mt-1 rounded-lg bg-blue-500/90 hover:bg-blue-500 active:scale-[0.97]
                                       transition-all text-sm font-medium px-4 py-2 focus:outline-none
                                       focus-visible:ring-2 focus-visible:ring-blue-300"
                          >
                            Run
                          </button>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              ))}
            </div>
          </div>

          {/* Activity log */}
          <div className="glass rounded-2xl p-4 h-40 overflow-y-auto shrink-0">
            <p className="text-xs uppercase tracking-wider text-neutral-500 mb-2">Activity</p>
            {log.length === 0 && <p className="text-xs text-neutral-600">No actions run yet.</p>}
            {log.map((entry, i) => (
              <p key={i} className={`text-xs mb-1 font-mono ${entry.ok ? "text-emerald-300" : "text-red-300"}`}>
                {entry.text}
              </p>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function FieldRenderer({
  schema, value, onChange, onToggleCore, processes, cpuCount,
}: {
  schema: ParamSchema;
  value: any;
  onChange: (v: any) => void;
  onToggleCore: (core: number) => void;
  processes: ProcessInfo[];
  cpuCount: number;
}) {
  const baseInput =
    "rounded-lg bg-black/30 border border-white/10 px-3 py-2 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400";

  switch (schema.type) {
    case "process_select":
      return (
        <label className="flex flex-col gap-1 text-xs text-neutral-400">
          {schema.label}
          <select value={value || ""} onChange={(e) => onChange(e.target.value)} className={baseInput}>
            <option value="">Select a program...</option>
            {processes.map((p) => (
              <option key={p.pid} value={p.name}>{p.name} (PID {p.pid})</option>
            ))}
          </select>
        </label>
      );
    case "core_multiselect": {
      const selected: number[] = value || [];
      return (
        <div className="flex flex-col gap-1 text-xs text-neutral-400">
          {schema.label}
          <div className="flex flex-wrap gap-1.5">
            {Array.from({ length: cpuCount }, (_, c) => c).map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => onToggleCore(c)}
                className={`w-9 h-9 rounded-lg text-xs font-mono border transition-colors ${
                  selected.includes(c)
                    ? "bg-blue-500/90 border-blue-400 text-white"
                    : "bg-white/5 border-white/10 text-neutral-400 hover:bg-white/10"
                }`}
              >
                {c}
              </button>
            ))}
          </div>
        </div>
      );
    }
    case "select":
      return (
        <label className="flex flex-col gap-1 text-xs text-neutral-400">
          {schema.label}
          <select value={value || ""} onChange={(e) => onChange(e.target.value)} className={baseInput}>
            <option value="">Select...</option>
            {(schema.options || []).map((o) => (
              <option key={o} value={o}>{o.replace(/_/g, " ")}</option>
            ))}
          </select>
        </label>
      );
    case "number":
      return (
        <label className="flex flex-col gap-1 text-xs text-neutral-400">
          {schema.label}
          <input type="number" value={value ?? ""} onChange={(e) => onChange(Number(e.target.value))} className={baseInput} />
        </label>
      );
    case "checkbox":
      return (
        <label className="flex items-center gap-2 text-xs text-neutral-400">
          <input type="checkbox" checked={!!value} onChange={(e) => onChange(e.target.checked)} className="accent-blue-500" />
          {schema.label}
        </label>
      );
    case "text":
    default:
      return (
        <label className="flex flex-col gap-1 text-xs text-neutral-400">
          {schema.label}
          <input type="text" value={value || ""} onChange={(e) => onChange(e.target.value)} className={baseInput} />
        </label>
      );
  }
}
