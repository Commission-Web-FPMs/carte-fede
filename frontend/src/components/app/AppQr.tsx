import { useEffect, useMemo, useState } from "react";
import { fetchCurrentUser } from "../../lib/current-user";

type Membership = {
  annee: number;
  annee_code?: string;
};

function formatAcademicYear(start: number): string {
  return `${start}-${start + 1}`;
}

export default function AppQr() {
  const [loading, setLoading] = useState(true);
  const [memberships, setMemberships] = useState<Membership[]>([]);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [qrSrc, setQrSrc] = useState<string>("");

  useEffect(() => {
    const load = async () => {
      try {
        const me = await fetchCurrentUser();
        if (!me.ok) {
          window.location.href = "/login?next=" + encodeURIComponent(window.location.pathname);
          return;
        }

        const res = await fetch("/api/memberships", { credentials: "include" });
        const data = res.ok ? await res.json() : [];
        const list = Array.isArray(data) ? data : [];
        list.sort((a: Membership, b: Membership) => b.annee - a.annee);
        setMemberships(list);

        if (list.length > 0) {
          const year = list[0].annee;
          setSelectedYear(year);
          setQrSrc(`/api/qr/${year}.png?ts=${Date.now()}`);
        }
      } catch {
        setMemberships([]);
      } finally {
        setLoading(false);
      }
    };

    load();
  }, []);

  const selectedMembership = useMemo(() => {
    return memberships.find((m) => m.annee === selectedYear) ?? null;
  }, [memberships, selectedYear]);

  const regenerate = () => {
    if (!selectedYear) return;
    setQrSrc(`/api/qr/${selectedYear}.png?ts=${Date.now()}`);
  };

  if (loading) {
    return <p className="mx-auto max-w-5xl p-8 text-slate-500">Chargement du QR...</p>;
  }

  if (!memberships.length) {
    return (
      <section className="mx-auto mt-8 w-full max-w-5xl rounded-3xl border border-slate-200 bg-white p-8 text-slate-500 shadow-sm">
        Aucune carte active: impossible de générer un QR.
      </section>
    );
  }

  return (
    <section className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-5 sm:px-8 sm:py-8">
      <header className="grid gap-4 rounded-3xl border border-slate-200 bg-white/90 p-5 shadow-sm md:grid-cols-[1fr_auto] md:items-center sm:p-8">
        <div>
          <h1 className="text-4xl font-black tracking-tight text-slate-900">Mon QR - Carte Fede</h1>
          <p className="mt-2 max-w-2xl text-base leading-relaxed text-slate-500">
            Présentez ce QR code pour prouver votre adhésion lors des contrôles. Sélectionnez une période pour générer automatiquement le QR correspondant.
          </p>
        </div>
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm font-semibold text-emerald-700">
          Identifiant associe: {selectedMembership?.annee_code ?? "-"}
        </div>
      </header>

      <div className="grid gap-4 lg:grid-cols-[300px_1fr]">
        <aside className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <label htmlFor="period" className="text-sm font-semibold text-slate-600">
            Selectionne la periode:
          </label>
          <select
            id="period"
            value={selectedYear ?? ""}
            onChange={(e) => {
              const year = Number(e.target.value);
              setSelectedYear(year);
              setQrSrc(`/api/qr/${year}.png?ts=${Date.now()}`);
            }}
            className="mt-3 w-full rounded-xl border border-slate-300 px-3 py-3 text-base font-semibold text-slate-700 outline-none transition focus:border-blue-500"
          >
            {memberships.map((m) => (
              <option key={m.annee} value={m.annee}>
                {formatAcademicYear(m.annee)} - {m.annee_code ?? "-"}
              </option>
            ))}
          </select>

          <button
            type="button"
            onClick={regenerate}
            className="mt-4 inline-flex items-center justify-center rounded-full bg-gradient-to-r from-blue-600 to-indigo-500 px-5 py-2 text-sm font-bold text-white transition hover:from-blue-700 hover:to-indigo-600"
          >
            Regenerer le QR
          </button>
        </aside>

        <article className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
          <p className="text-center text-xs font-semibold uppercase tracking-[0.3em] text-blue-400">QR securise</p>
          <h2 className="mt-1 text-center text-3xl font-black text-slate-900">
            {selectedYear ? formatAcademicYear(selectedYear) : "-"}
          </h2>

          <div className="mx-auto mt-6 w-fit rounded-3xl border border-slate-200 bg-slate-50 p-5">
            <img
              src={qrSrc}
              alt={selectedYear ? `QR carte ${formatAcademicYear(selectedYear)}` : "QR carte"}
              className="h-64 w-64 rounded-lg bg-white object-contain"
            />
          </div>
        </article>
      </div>
    </section>
  );
}
