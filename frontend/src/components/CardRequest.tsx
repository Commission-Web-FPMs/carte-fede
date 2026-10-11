import { useEffect, useState } from "react";
import { cardRequestState } from "../lib/card-request-state.mjs";

type Card = { annee: number; annee_code: string };
type Request = { annee: number; status: string; free_card: boolean };

export default function CardRequest() {
  const current = new Date().getMonth() >= 7 ? new Date().getFullYear() : new Date().getFullYear() - 1;
  const [year, setYear] = useState(current);
  const [visible, setVisible] = useState(false);
  const [cards, setCards] = useState<Card[]>([]);
  const [requests, setRequests] = useState<Request[]>([]);
  const [busy, setBusy] = useState(false);
  const [freeRequested, setFreeRequested] = useState(false);
  const [message, setMessage] = useState("");
  const [confirmation, setConfirmation] = useState(false);
  const [registrationState, setRegistrationState] = useState("");
  async function refresh() {
    const responses = await Promise.all([fetch("/api/memberships", { credentials: "include" }), fetch("/api/memberships/requests", { credentials: "include" })]);
    if (responses.some(r => !r.ok)) { setVisible(false); return; }
    const [c, r] = await Promise.all(responses.map(r => r.json()));
    setCards(c); setRequests(r); setVisible(true);
  }
  useEffect(() => {
    refresh().catch(() => setVisible(false));
    fetch('/api/dev/enrollment-notice', { credentials: 'include' }).then(r => r.ok ? r.json() : null).then(d => { setConfirmation(d?.pending_confirmation === true); setRegistrationState(d?.state || ""); }).catch(() => {});
  }, []);
  async function submit() {
    if (busy) return;
    setBusy(true); setMessage("");
    try {
      const response = await fetch("/api/memberships/requests", { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ annee: year, free_card_requested: freeRequested }) });
      const data = await response.json();
      setMessage(response.ok ? "Votre demande a été enregistrée. Aucun paiement n’est effectué depuis cette page." : data.error || "Demande indisponible.");
      await refresh();
    } catch { setMessage("Connexion indisponible. Vérifiez le statut avant de réessayer."); }
    finally { setBusy(false); }
  }
  const notices: Record<string, string> = {
    pending: "Votre inscription a été enregistrée et attend la validation d'un administrateur.",
    activating: "Votre inscription est en cours de validation. Aucun accès métier n’est encore accordé.",
    rejected: "Votre inscription a été refusée. Contactez un administrateur.",
    approved: "Votre inscription est validée. Vous pouvez maintenant vous connecter.",
    historical: "Votre inscription nécessite une activation opérateur séparée.",
  };
  if (!visible) return confirmation ? <section role="status" className="mx-auto max-w-5xl rounded-xl bg-blue-50 p-6">{notices[registrationState] || notices.pending}{registrationState === "approved" && <a className="ml-3 underline" href="/api/auth/oidc/login">Se connecter</a>}</section> : null;
  const state = cardRequestState(cards, requests, year);
  const pending = requests.find(r => r.annee === year);
  return <section className="mx-auto max-w-5xl space-y-4 rounded-xl border-l-4 border-blue-900 bg-white p-6 shadow-box">
    <h2 className="text-xl font-semibold">Demander une carte Fédé</h2>
    <label className="flex flex-wrap items-center gap-3">Année académique
      <select value={year} onChange={e => { setYear(Number(e.target.value)); setMessage(""); }} disabled={busy} className="rounded border p-2">
        {[current, current + 1].map(y => <option key={y} value={y}>{y}–{y + 1}</option>)}
      </select>
    </label>
    {state === "card" ? <div className="flex flex-wrap gap-4"><a className="underline" href="/cartes/">Mes cartes</a><a className="underline" href={`/api/qr/${year}.png`}>Afficher mon QR de carte</a></div> : !["absent", "rejected"].includes(state) ? <p>En attente de validation{state === "payment" ? " — paiement à confirmer par un administrateur" : ""}.</p> : <div className="space-y-3">
      {pending?.status === "rejected" && <p>Votre demande a été refusée. Vous pouvez soumettre une nouvelle demande ; une nouvelle validation sera nécessaire.</p>}
      <label className="flex items-center gap-3"><input type="checkbox" checked={freeRequested} disabled={busy} onChange={e => setFreeRequested(e.target.checked)} /> Je demande l’exemption BAC1 (validation administrative requise).</label>
      <button disabled={busy} onClick={submit} className="rounded bg-blue-900 px-4 py-3 text-white disabled:opacity-50">{busy ? "Enregistrement…" : "Demander ma carte Fédé"}</button>
    </div>}
    <p role="status" aria-live="polite">{message}</p>
  </section>;
}
