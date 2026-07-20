import { useState, type FormEvent } from "react";
import { Check, LoaderCircle, MapPinned, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface Props {
  open: boolean;
  suggestedName: string;
  areaHectares: number;
  vertexCount: number;
  pending: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: (name: string) => void;
}

export default function ConfirmBoundaryDialog({
  open,
  suggestedName,
  areaHectares,
  vertexCount,
  pending,
  error,
  onCancel,
  onConfirm,
}: Props) {
  const [name, setName] = useState(suggestedName);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalizedName = name.trim();
    if (normalizedName) onConfirm(normalizedName);
  };

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => !nextOpen && onCancel()}>
      <DialogContent
        showCloseButton={!pending}
        className="border-slate-700 bg-slate-950 text-slate-100 sm:max-w-md"
      >
        <DialogHeader>
          <div className="mb-1 flex h-10 w-10 items-center justify-center rounded-md bg-lime-400/15 text-lime-400">
            <MapPinned className="h-5 w-5" />
          </div>
          <DialogTitle>Conferma il confine</DialogTitle>
          <DialogDescription className="text-slate-400">
            Assegna un nome al campo prima di salvarlo.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 border-y border-slate-800 py-4">
          <BoundaryMetric label="Superficie stimata" value={`${formatArea(areaHectares)} ha`} />
          <BoundaryMetric label="Vertici" value={vertexCount.toLocaleString("it-IT")} />
        </div>

        <form className="space-y-5" onSubmit={handleSubmit}>
          <div className="space-y-2">
            <Label htmlFor="field-name" className="text-slate-300">
              Nome campo
            </Label>
            <Input
              id="field-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={160}
              autoComplete="off"
              autoFocus
              required
              disabled={pending}
              className="border-slate-700 bg-slate-900 text-slate-100"
            />
          </div>
          {error && (
            <p role="alert" className="border-l-2 border-rose-400 pl-3 text-sm text-rose-300">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={onCancel}
              disabled={pending}
              className="border-slate-700 bg-slate-950 text-slate-300 hover:bg-slate-800 hover:text-white"
            >
              <X /> Annulla
            </Button>
            <Button
              type="submit"
              disabled={!name.trim() || pending}
              className="bg-lime-400 text-slate-950 hover:bg-lime-300"
            >
              {pending ? <LoaderCircle className="animate-spin" /> : <Check />}
              {pending ? "Salvataggio" : "Salva campo"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function BoundaryMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase text-slate-500">{label}</div>
      <div className="mt-1 text-lg font-semibold text-slate-100">{value}</div>
    </div>
  );
}

function formatArea(value: number): string {
  return value.toLocaleString("it-IT", {
    minimumFractionDigits: value < 10 ? 2 : 1,
    maximumFractionDigits: value < 10 ? 2 : 1,
  });
}