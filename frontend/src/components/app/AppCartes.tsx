import { useEffect, useMemo, useState } from "react";
import { fetchCurrentUser } from "../../lib/current-user";
import { academicYear, currentYear, request } from "../../lib/admin-users";

type Membership = {
  annee: number;
  annee_code?: string;
};
type CardRequest = { annee: number; status: "payment_required" | "pending" | "rejected"; free_card?: boolean };
type Payment = { annee: number; beneficiary: string; iban: string; bic: string; amount: string; communication_prefix: string };

function formatAcademicYear(start: number): string {
  return `${start}-${start + 1}`;
}

function padCode(code?: string): string {
  if (!code) return "-";
  return code.replace(/-/g, " - ");
}

export default function AppCartes() {
  const [loading, setLoading] = useState(true);
  const [memberships, setMemberships] = useState<Membership[]>([]);
  const [copyMessage, setCopyMessage] = useState<string>("");
  const [requests, setRequests] = useState<CardRequest[]>([]);
  const [requestYear, setRequestYear] = useState(currentYear());
  const [requestMessage, setRequestMessage] = useState("");
  const [requestError, setRequestError] = useState(false);
  const [requestBusy, setRequestBusy] = useState(false);
  const [payment, setPayment] = useState<Payment | null>(null);
  const [paymentQr, setPaymentQr] = useState("");
  const [paymentError, setPaymentError] = useState("");
  const [accountName, setAccountName] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        const me = await fetchCurrentUser();
        if (!me.ok) {
          window.location.href =
            "/login?next=" + encodeURIComponent(window.location.pathname);
          return;
        }
        const account = await me.json();
        setAccountName(`${(account.nom || "NOM").toUpperCase()} ${account.prenom || "Prénom"}`);

        await Promise.all([
          request("/api/memberships")
            .then((response) => response.json())
            .then((data) => {
              const list = Array.isArray(data) ? data : [];
              list.sort((a: Membership, b: Membership) => b.annee - a.annee);
              setMemberships(list);
            })
            .catch(() => setMemberships([])),
          request("/api/memberships/requests")
            .then((response) => response.json())
            .then(setRequests)
            .catch(() => {
              setRequestError(true);
              setRequestMessage("Impossible de charger vos demandes de carte. Réessayez en rechargeant la page.");
            }),
          fetch("/api/card-payment", { cache: "no-store" })
            .then((response) => response.json())
            .then(setPayment)
            .catch(() => setPaymentError("Coordonnées de paiement indisponibles.")),
        ]);
      } catch {
        setMemberships([]);
      } finally {
        setLoading(false);
      }
    };

    load();
  }, []);

  const updatedLabel = useMemo(() => {
    return new Intl.DateTimeFormat("fr-BE", {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date());
  }, []);

  const copyIdentifier = async (value?: string) => {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      setCopyMessage(`Identifiant ${value} copié.`);
    } catch {
      setCopyMessage("Copie impossible sur ce navigateur.");
    }
    window.setTimeout(() => setCopyMessage(""), 2200);
  };

  async function askForCard() {
    if (requestBusy) return;
    setRequestBusy(true);
    setRequestMessage("");
    setRequestError(false);
    try {
      await request("/api/memberships/requests", "POST", {
        annee: requestYear,
      });
      setRequests((previous) => [
        ...previous.filter((item) => item.annee !== requestYear),
        { annee: requestYear, status: "payment_required" },
      ]);
      setRequestMessage("Demande envoyée : paiement requis, puis validation par un administrateur.");
    } catch (error) {
      setRequestError(true);
      setRequestMessage(
        error instanceof Error
          ? error.message
          : "Demande impossible. Réessayez.",
      );
    } finally {
      setRequestBusy(false);
    }
  }

  async function generatePaymentQr() {
    setPaymentError("");
    try {
      const response = await request("/api/card-payment/qr", "POST", { annee: requestYear });
      if (paymentQr) URL.revokeObjectURL(paymentQr);
      setPaymentQr(URL.createObjectURL(await response.blob()));
    } catch (error) {
      setPaymentError(error instanceof Error ? error.message : "QR de paiement indisponible.");
    }
  }

  if (loading) {
    return (
      <p className="mx-auto max-w-5xl p-8 text-slate-500">
        Chargement des cartes...
      </p>
    );
  }

  return (
    <section className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-5 sm:px-8 sm:py-8">
      <header className="rounded-3xl border border-slate-200 bg-white/90 p-5 shadow-sm sm:p-8">
        <div className="grid gap-5 md:grid-cols-[1fr_auto] md:items-start">
          <div>
            <h1 className="text-4xl font-black tracking-tight text-slate-900">
              Mes cartes
            </h1>
            <p className="mt-2 max-w-xl text-base leading-relaxed text-slate-500">
              Retrouvez ici l&apos;ensemble de vos cartes d&apos;adhésion
              actives. Présentez l&apos;identifiant pour prouver votre statut
              lors des événements et contrôles.
            </p>
          </div>
          <a
            href="/app/qr"
            className="inline-flex items-center justify-center rounded-full bg-gradient-to-r from-blue-600 to-indigo-500 px-6 py-3 text-base font-bold text-white shadow-sm transition hover:from-blue-700 hover:to-indigo-600"
          >
            Générer mon QR
          </a>
        </div>

        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          <div className="rounded-2xl border border-slate-200 bg-slate-50/70 px-4 py-3">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-blue-500">
              Cartes actives
            </p>
            <p className="mt-1 text-4xl font-black text-slate-900">
              {memberships.length}
            </p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-slate-50/70 px-4 py-3">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-blue-500">
              Dernière mise à jour
            </p>
            <p className="mt-1 text-3xl font-black text-slate-900">
              {updatedLabel}
            </p>
          </div>
        </div>
      </header>

      <section
        className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6"
        aria-labelledby="card-request-title"
      >
        <h2
          id="card-request-title"
          className="text-xl font-semibold text-blue-900"
        >
          Demander une carte Fédé
        </h2>
        <p className="mt-1 text-sm text-slate-600">
          Votre carte sera créée après validation par un administrateur.
        </p>
        <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="block flex-1 text-sm font-medium text-slate-700">
            Année académique
            <select
              className="mt-2 min-h-11 w-full rounded-xl border border-slate-300 bg-white px-3 text-base"
              value={requestYear}
              onChange={(event) => {
                setRequestYear(Number(event.target.value));
                if (paymentQr) URL.revokeObjectURL(paymentQr);
                setPaymentQr("");
              }}
            >
              {[currentYear(), currentYear() + 1].map((year) => (
                <option value={year} key={year}>
                  {academicYear(String(year))}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={() => void askForCard()}
            disabled={
              requestBusy ||
              memberships.some((item) => item.annee === requestYear) ||
              requests.some(
                (item) =>
                  item.annee === requestYear && item.status !== "rejected",
              )
            }
            className="min-h-11 rounded-xl bg-blue-900 px-4 py-2 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {requestBusy ? "Envoi…" : "Demander cette carte"}
          </button>
        </div>
        {memberships.some((item) => item.annee === requestYear) && (
          <p className="mt-2 text-sm text-slate-600">
            Vous possédez déjà une carte pour cette année.
          </p>
        )}
        {requests.map((item) => (
          <p className="mt-2 text-sm text-slate-700" key={item.annee}>
            {academicYear(String(item.annee))} :{" "}
            {item.status === "pending"
              ? "en attente de validation"
              : item.status === "payment_required"
                ? "paiement requis"
              : "demande refusée, vous pouvez en envoyer une nouvelle"}
          </p>
        ))}
        {requests.some((item) => item.annee === requestYear && item.status === "payment_required") && (
          <div className="mt-4 rounded-2xl border border-blue-200 bg-blue-50 p-4 text-sm text-slate-700">
            <p className="font-semibold text-blue-900">Paiement de la carte Fédé</p>
            <p className="mt-2">Effectuez un virement avec la communication : <strong>{accountName} – {payment?.communication_prefix || "Carte Fédé"} {academicYear(String(requestYear))}</strong>.</p>
            {payment?.beneficiary && payment?.iban && payment?.amount ? (
              <>
                <p className="mt-2 break-words">{payment.beneficiary} · {payment.iban} · {payment.amount} €{payment.bic ? ` · ${payment.bic}` : ""}</p>
                <button type="button" className="mt-3 min-h-11 rounded-xl bg-blue-900 px-4 py-2 font-semibold text-white" onClick={() => void generatePaymentQr()}>Générer le QR de paiement EPC</button>
                {paymentQr && <img src={paymentQr} alt="QR de paiement EPC à scanner dans votre application bancaire" className="mt-3 w-56 max-w-full rounded-xl bg-white p-2" />}
              </>
            ) : <p className="mt-2">Coordonnées de paiement non encore configurées. Revenez plus tard.</p>}
            {paymentError && <p role="alert" className="mt-2 text-red-700">{paymentError}</p>}
          </div>
        )}
        {requestMessage && (
          <p
            role={requestError ? "alert" : "status"}
            className={`mt-3 rounded-xl p-3 text-sm ${requestError ? "bg-red-50 text-red-800" : "bg-blue-50 text-blue-900"}`}
          >
            {requestMessage}
          </p>
        )}
      </section>

      {!memberships.length ? (
        <article className="rounded-3xl border border-slate-200 bg-white p-8 text-slate-500 shadow-sm">
          Aucune carte active disponible.
        </article>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {memberships.map((item) => (
            <article
              key={item.annee}
              className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6"
            >
              <div className="flex items-center justify-between gap-3">
                <p className="text-xs font-semibold uppercase tracking-[0.24em] text-blue-500">
                  Période
                </p>
                <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-bold uppercase tracking-[0.16em] text-emerald-700">
                  Validée
                </span>
              </div>

              <h2 className="mt-1 text-3xl font-black text-slate-900">
                {formatAcademicYear(item.annee)}
              </h2>

              <p className="mt-6 text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
                Identifiant
              </p>
              <div className="mt-2 rounded-xl bg-slate-100 px-4 py-3 text-2xl font-extrabold tracking-wide text-slate-700">
                {padCode(item.annee_code)}
              </div>

              <button
                type="button"
                onClick={() => copyIdentifier(item.annee_code)}
                className="mt-5 inline-flex items-center justify-center rounded-full bg-gradient-to-r from-blue-600 to-indigo-500 px-5 py-2 text-sm font-bold text-white transition hover:from-blue-700 hover:to-indigo-600"
              >
                Copier l&apos;identifiant
              </button>
            </article>
          ))}
        </div>
      )}

      {copyMessage ? (
        <p className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm font-medium text-emerald-700">
          {copyMessage}
        </p>
      ) : null}
    </section>
  );
}
