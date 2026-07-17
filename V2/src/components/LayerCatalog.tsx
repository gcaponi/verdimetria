import { useState } from "react";
import {
  Check,
  ChevronDown,
  Database,
  Layers3,
  LoaderCircle,
  LockKeyhole,
  Search,
  Satellite,
  Sprout,
} from "lucide-react";
import type { WmsLayer, WmsLayerGroup } from "@/lib/wms";
import { cn } from "@/lib/utils";

interface Props {
  layers: WmsLayer[];
  activeLayerId: string;
  onLayerChange: (layerId: string) => void;
  catalogLoading: boolean;
  catalogError: string | null;
}

const GROUPS: Array<{
  id: WmsLayerGroup;
  label: string;
  icon: typeof Layers3;
}> = [
  { id: "base", label: "Mappa di base", icon: Layers3 },
  { id: "vegetation", label: "Vegetazione e compositi", icon: Satellite },
  { id: "soil", label: "Suolo modellato", icon: Sprout },
  { id: "analysis", label: "Analisi quantitative", icon: Database },
  { id: "cdse-catalog", label: "Catalogo CDSE completo", icon: Satellite },
];

export default function LayerCatalog({
  layers,
  activeLayerId,
  onLayerChange,
  catalogLoading,
  catalogError,
}: Props) {
  const [query, setQuery] = useState("");
  const normalizedQuery = query.trim().toLocaleLowerCase("it");
  const visibleLayers = normalizedQuery
    ? layers.filter((layer) =>
        `${layer.label} ${layer.id} ${layer.detail}`.toLocaleLowerCase("it").includes(normalizedQuery)
      )
    : layers;
  const liveCount = layers.filter((layer) => layer.provider !== "pending").length;

  return (
    <section className="overflow-hidden border-y border-slate-800 bg-slate-900/30">
      <div className="border-b border-slate-800 p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-lime-400">
              Layer mappa
            </p>
            <h2 className="mt-1 text-base font-semibold text-white">Catalogo dati</h2>
          </div>
          <span className="rounded-md border border-emerald-400/20 bg-emerald-400/10 px-2 py-1 text-[10px] font-semibold uppercase text-emerald-300">
            {liveCount} live
          </span>
        </div>
        <label className="relative mt-3 block">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Cerca layer o indice"
            className="h-10 w-full rounded-lg border border-slate-700 bg-slate-950 pl-9 pr-3 text-sm text-slate-100 outline-none placeholder:text-slate-600 focus:border-lime-400/60"
          />
        </label>
      </div>

      <div className="max-h-[32rem] overflow-y-auto p-2">
        {GROUPS.map((group) => {
          const groupLayers = visibleLayers.filter((layer) => layer.group === group.id);
          if (!groupLayers.length && !(group.id === "cdse-catalog" && catalogLoading)) return null;
          const GroupIcon = group.icon;
          const isFullCatalog = group.id === "cdse-catalog";

          return (
            <details
              key={group.id}
              className="group/catalog border-b border-slate-800/70 last:border-b-0"
              open={!isFullCatalog || Boolean(normalizedQuery)}
            >
              <summary className="flex cursor-pointer list-none items-center gap-2 px-2 py-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-400">
                <GroupIcon className="h-3.5 w-3.5" />
                <span className="min-w-0 flex-1">{group.label}</span>
                {isFullCatalog && catalogLoading ? (
                  <LoaderCircle className="h-3.5 w-3.5 animate-spin text-cyan-300" />
                ) : (
                  <span className="text-[10px] text-slate-600">{groupLayers.length}</span>
                )}
                <ChevronDown className="h-3.5 w-3.5 transition-transform group-open/catalog:rotate-180" />
              </summary>
              <div className="space-y-1 pb-3">
                {groupLayers.map((layer) => (
                  <LayerRow
                    key={layer.id}
                    layer={layer}
                    active={activeLayerId === layer.id}
                    onSelect={() => onLayerChange(layer.id)}
                  />
                ))}
                {isFullCatalog && catalogLoading && (
                  <p className="px-2 py-2 text-xs text-slate-500">Caricamento capabilities CDSE...</p>
                )}
                {isFullCatalog && catalogError && (
                  <p className="mx-2 rounded-md border border-rose-400/20 bg-rose-400/10 p-2 text-xs text-rose-200">
                    {catalogError}
                  </p>
                )}
              </div>
            </details>
          );
        })}
        {!visibleLayers.length && (
          <p className="px-3 py-8 text-center text-sm text-slate-500">Nessun layer corrispondente.</p>
        )}
      </div>
    </section>
  );
}

function LayerRow({
  layer,
  active,
  onSelect,
}: {
  layer: WmsLayer;
  active: boolean;
  onSelect: () => void;
}) {
  const pending = layer.provider === "pending";
  const providerLabel =
    layer.provider === "soilgrids"
      ? "SoilGrids"
      : layer.provider === "cdse"
        ? "CDSE"
        : layer.provider === "pending"
          ? "Backend"
          : "Base";

  return (
    <button
      type="button"
      onClick={onSelect}
      disabled={pending}
      aria-pressed={active}
      className={cn(
        "flex w-full items-start gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors",
        active
          ? "border-lime-400/50 bg-lime-400/10"
          : "border-transparent hover:border-slate-700 hover:bg-slate-800/70",
        pending && "cursor-not-allowed opacity-70 hover:border-transparent hover:bg-transparent"
      )}
    >
      <span
        className={cn(
          "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border",
          active ? "border-lime-300 bg-lime-300 text-slate-950" : "border-slate-600 text-slate-600",
          pending && "border-slate-700"
        )}
      >
        {pending ? <LockKeyhole className="h-3 w-3" /> : active ? <Check className="h-3 w-3" /> : null}
      </span>
      <span className="min-w-0 flex-1">
        <span className={cn("block text-[13px] font-medium", active ? "text-lime-200" : "text-slate-200")}>{layer.label}</span>
        <span className="mt-0.5 block text-[11px] leading-relaxed text-slate-500">{layer.detail}</span>
      </span>
      <span className="shrink-0 rounded border border-slate-700 px-1.5 py-0.5 text-[9px] font-semibold uppercase text-slate-500">
        {providerLabel}
      </span>
    </button>
  );
}