import { useEffect, useState } from "react";
import type { MapArea } from "@/types";
import { Card, SectionTitle } from "@/components/ui-bits";
import { fieldCentroid, fmt } from "@/lib/data";
import { Thermometer, Droplets, Wind, CloudRain } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

interface WxDaily {
  time: string[];
  temperature_2m_max: number[];
  temperature_2m_min: number[];
  precipitation_sum: number[];
}
interface Wx {
  current: { temperature_2m: number; relative_humidity_2m: number; wind_speed_10m: number; precipitation: number };
  daily: WxDaily;
}

export default function WeatherSection({ field }: { field: MapArea }) {
  const [wx, setWx] = useState<Wx | null>(null);
  const [err, setErr] = useState(false);
  const [lon, lat] = fieldCentroid(field);

  useEffect(() => {
    setWx(null);
    setErr(false);
    const url =
      `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}` +
      `&current=temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation` +
      `&daily=temperature_2m_max,temperature_2m_min,precipitation_sum` +
      `&past_days=14&forecast_days=7&timezone=Europe%2FRome`;
    fetch(url)
      .then((r) => r.json())
      .then((j) => setWx(j))
      .catch(() => setErr(true));
  }, [lon, lat]);

  if (err)
    return (
      <Card>
        <p className="text-[13px] text-slate-400">
          Dati meteo non raggiungibili (Open-Meteo). Controlla la connessione: il servizio è
          gratuito e non richiede chiavi.
        </p>
      </Card>
    );
  if (!wx)
    return (
      <Card>
        <p className="animate-pulse text-[13px] text-slate-500">
          Caricamento meteo per {field.name} ({lat.toFixed(3)}, {lon.toFixed(3)})…
        </p>
      </Card>
    );

  const now = wx.current;
  const d = wx.daily;
  const todayIdx = d.time.findIndex((t) => t === new Date().toISOString().slice(0, 10));
  const hist = d.time.slice(0, todayIdx + 1).map((t, i) => ({
    day: t.slice(5).split("-").reverse().join("/"),
    rain: d.precipitation_sum[i],
  }));
  const forecast = d.time.slice(todayIdx, todayIdx + 7).map((t, i) => ({
    date: t,
    max: d.temperature_2m_max[todayIdx + i],
    min: d.temperature_2m_min[todayIdx + i],
    rain: d.precipitation_sum[todayIdx + i],
  }));

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <WxKpi icon={<Thermometer className="h-4 w-4" />} label="Temperatura" value={`${fmt(now.temperature_2m, 1)} °C`} />
        <WxKpi icon={<Droplets className="h-4 w-4" />} label="Umidità" value={`${now.relative_humidity_2m}%`} />
        <WxKpi icon={<Wind className="h-4 w-4" />} label="Vento" value={`${fmt(now.wind_speed_10m, 0)} km/h`} />
        <WxKpi icon={<CloudRain className="h-4 w-4" />} label="Pioggia odierna" value={`${fmt(now.precipitation, 1)} mm`} />
      </div>

      <Card>
        <SectionTitle kicker="Ultimi 14 giorni" title="Precipitazioni (mm)" />
        <div className="h-40">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={hist} margin={{ top: 4, right: 8, left: -22, bottom: 0 }}>
              <XAxis dataKey="day" tick={{ fill: "#94a3b8", fontSize: 10 }} tickLine={false} axisLine={{ stroke: "#334155" }} />
              <YAxis tick={{ fill: "#94a3b8", fontSize: 10 }} tickLine={false} axisLine={false} />
              <Tooltip
                contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 8, fontSize: 12 }}
                formatter={(v: number) => [`${fmt(v, 1)} mm`, "Pioggia"]}
              />
              <Bar dataKey="rain" fill="#38bdf8" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card>
        <SectionTitle kicker="Prossimi 7 giorni" title="Previsioni" />
        <div className="grid grid-cols-7 gap-2 text-center">
          {forecast.map((f) => (
            <div key={f.date} className="rounded-lg border border-slate-800 bg-slate-950 px-1 py-2">
              <div className="text-[10px] text-slate-500">
                {new Date(f.date + "T12:00").toLocaleDateString("it-IT", { weekday: "short" })}
              </div>
              <div className="mt-1 text-[13px] font-semibold text-slate-100">{Math.round(f.max)}°</div>
              <div className="text-[11px] text-slate-500">{Math.round(f.min)}°</div>
              <div className="mt-1 text-[10px] text-sky-400">{f.rain > 0 ? `${fmt(f.rain, 1)}mm` : "—"}</div>
            </div>
          ))}
        </div>
        <p className="mt-3 text-[11px] text-slate-500">
          Fonte: Open-Meteo (tempo reale), coordinate del centroide del campo. Utile per
          pianificare concimazioni e interpretare l'NDVI degli ultimi rilievi.
        </p>
      </Card>
    </div>
  );
}

function WxKpi({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-slate-500">
        {icon} {label}
      </div>
      <div className="mt-1 text-xl font-bold text-slate-100">{value}</div>
    </Card>
  );
}
