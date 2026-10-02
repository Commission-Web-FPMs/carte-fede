import { useEffect, useState, type FormEvent } from "react";
import {
  academicYear,
  currentYear,
  PREFIXES,
  request,
} from "../lib/admin-users";

type Registration = {
  id: string;
  nom: string;
  prenom: string;
  member_id: string;
  expires_at: string;
};
type CardRequest = {
  id: string;
  nom: string;
  prenom: string;
  identifiant: string;
  annee: number;
};
type Queue = { registrations: Registration[]; cards: CardRequest[] };

export default function AdminRequests({
  onChanged,
}: {
  onChanged: () => void;
}) {
  const [queue, setQueue] = useState<Queue>({ registrations: [], cards: [] });
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [confirmReject, setConfirmReject] = useState("");
  const [cardFor, setCardFor] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    try {
      setQueue(await (await request("/api/admin/requests")).json());
      setError("");
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Chargement des demandes impossible.",
      );
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void load();
  }, []);

  async function decide(
    kind: "registrations" | "card-requests",
    id: string,
    decision: "approve" | "reject",
    body: object = {},
  ) {
    if (busy) return;
    setBusy(id);
    setError("");
    setNotice("");
    try {
      await request(`/api/admin/${kind}/${id}/${decision}`, "POST", body);
      await load();
      if (decision === "approve") onChanged();
      setConfirmReject("");
      setNotice(
        decision === "approve" ? "Demande validée." : "Demande refusée.",
      );
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Opération impossible. Réessayez.",
      );
    } finally {
      setBusy("");
    }
  }

  function approveRegistration(event: FormEvent<HTMLFormElement>, id: string) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    void decide("registrations", id, "approve", {
      add_card: values.has("add_card"),
      annee: Number(values.get("annee")),
      prefix: values.get("prefix"),
    });
  }

  return (
    <section
      className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6"
      aria-labelledby="requests-title"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="requests-title" className="text-xl font-semibold text-blue-900">
          Demandes à valider
        </h2>
        <button
          className="admin-button admin-secondary text-sm"
          disabled={!!busy || loading}
          onClick={() => void load()}
        >
          Actualiser
        </button>
      </div>
      {error && (
        <p role="alert" className="admin-error mt-3">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="admin-success mt-3">
          {notice}
        </p>
      )}
      {loading ? (
        <p className="mt-3 text-sm text-slate-600">Chargement des demandes…</p>
      ) : (
        <>
          {!queue.registrations.length && !queue.cards.length && (
            <p className="mt-3 text-sm text-slate-600">
              Aucune demande en attente.
            </p>
          )}
          {!!queue.registrations.length && (
            <div className="mt-4 space-y-3">
              <h3 className="font-semibold text-slate-800">
                Inscriptions ({queue.registrations.length})
              </h3>
              {queue.registrations.map((item) => (
                <article
                  key={item.id}
                  className="rounded-2xl border border-slate-200 bg-slate-50 p-3 sm:p-4"
                >
                  <p className="font-semibold text-slate-900">
                    {item.prenom} {item.nom}
                  </p>
                  <p className="text-sm text-slate-600">
                    Matricule {item.member_id} · valable jusqu’au{" "}
                    {new Date(`${item.expires_at}Z`).toLocaleDateString(
                      "fr-BE",
                    )}
                  </p>
                  <form
                    className="mt-3 space-y-3"
                    onSubmit={(event) => approveRegistration(event, item.id)}
                  >
                    <label className="flex min-h-11 items-center gap-2 text-sm text-slate-700">
                      <input
                        type="checkbox"
                        name="add_card"
                        checked={cardFor === item.id}
                        onChange={(event) =>
                          setCardFor(event.target.checked ? item.id : "")
                        }
                      />{" "}
                      Ajouter une carte lors de la validation
                    </label>
                    {cardFor === item.id && (
                      <div className="grid grid-cols-2 gap-2">
                        <label className="admin-label">
                          Année
                          <select name="annee" className="admin-input">
                            {[currentYear(), currentYear() + 1].map((year) => (
                              <option key={year} value={year}>
                                {academicYear(String(year))}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label className="admin-label">
                          Préfixe
                          <select name="prefix" className="admin-input">
                            {PREFIXES.map((prefix) => (
                              <option key={prefix}>{prefix}</option>
                            ))}
                          </select>
                        </label>
                      </div>
                    )}
                    <div className="flex flex-wrap gap-2">
                      <button
                        className="admin-button admin-primary"
                        disabled={!!busy}
                      >
                        {busy === item.id ? "Validation…" : "Valider le compte"}
                      </button>
                      <button
                        type="button"
                        className="admin-button text-red-700"
                        disabled={!!busy}
                        onClick={() => setConfirmReject(`registration:${item.id}`)}
                      >
                        Refuser
                      </button>
                    </div>
                  </form>
                  {confirmReject === `registration:${item.id}` && (
                    <div className="mt-3 rounded-xl border border-red-200 p-3 text-sm">
                      <p>
                        Refuser l’inscription de {item.prenom} {item.nom} ?
                      </p>
                      <div className="mt-2 flex gap-2">
                        <button
                          className="admin-button admin-secondary"
                          onClick={() => setConfirmReject("")}
                        >
                          Annuler
                        </button>
                        <button
                          className="admin-button bg-red-700 text-white"
                          disabled={!!busy}
                          onClick={() =>
                            void decide("registrations", item.id, "reject")
                          }
                        >
                          Confirmer le refus
                        </button>
                      </div>
                    </div>
                  )}
                </article>
              ))}
            </div>
          )}
          {!!queue.cards.length && (
            <div className="mt-5 space-y-3">
              <h3 className="font-semibold text-slate-800">
                Cartes ({queue.cards.length})
              </h3>
              {queue.cards.map((item) => (
                <article
                  key={item.id}
                  className="rounded-2xl border border-slate-200 bg-slate-50 p-3 sm:p-4"
                >
                  <p className="font-semibold text-slate-900">
                    {item.prenom} {item.nom}
                  </p>
                  <p className="break-all text-sm text-slate-600">
                    {item.identifiant} · {academicYear(String(item.annee))}
                  </p>
                  <form
                    className="mt-3 flex flex-wrap items-end gap-2"
                    onSubmit={(event) => {
                      event.preventDefault();
                      void decide("card-requests", item.id, "approve", {
                        prefix: new FormData(event.currentTarget).get("prefix"),
                      });
                    }}
                  >
                    <label className="admin-label">
                      Préfixe
                      <select name="prefix" className="admin-input">
                        {PREFIXES.map((prefix) => (
                          <option key={prefix}>{prefix}</option>
                        ))}
                      </select>
                    </label>
                    <button
                      className="admin-button admin-primary"
                      disabled={!!busy}
                    >
                      {busy === item.id ? "Validation…" : "Attribuer la carte"}
                    </button>
                    <button
                      type="button"
                      className="admin-button text-red-700"
                      disabled={!!busy}
                      onClick={() => setConfirmReject(`card:${item.id}`)}
                    >
                      Refuser
                    </button>
                  </form>
                  {confirmReject === `card:${item.id}` && (
                    <div className="mt-3 rounded-xl border border-red-200 p-3 text-sm">
                      <p>
                        Refuser la demande de carte{" "}
                        {academicYear(String(item.annee))} ?
                      </p>
                      <div className="mt-2 flex gap-2">
                        <button
                          className="admin-button admin-secondary"
                          onClick={() => setConfirmReject("")}
                        >
                          Annuler
                        </button>
                        <button
                          className="admin-button bg-red-700 text-white"
                          disabled={!!busy}
                          onClick={() =>
                            void decide("card-requests", item.id, "reject")
                          }
                        >
                          Confirmer le refus
                        </button>
                      </div>
                    </div>
                  )}
                </article>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}
