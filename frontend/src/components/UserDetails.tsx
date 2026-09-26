import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  academicYear,
  currentYear,
  PREFIXES,
  request,
  ROLES,
  roleLabel,
  yearOptions,
  type User,
} from "../lib/admin-users";

type Props = {
  user: User;
  onChange: (user: User) => void;
  onDelete: () => void;
  onClose: () => void;
};
type Confirmation =
  | { kind: "user" | "discard" }
  | { kind: "card"; year: string };

export default function UserDetails({
  user,
  onChange,
  onDelete,
  onClose,
}: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const confirmCancelRef = useRef<HTMLButtonElement>(null);
  const busyRef = useRef(false);
  const [mode, setMode] = useState<"view" | "edit" | "card">("view");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState<{
    error: boolean;
    text: string;
  } | null>(null);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [cardYear, setCardYear] = useState(String(currentYear()));
  const [cardCode, setCardCode] = useState("");
  const base = `/api/admin/users/${user.id}`;
  const cards = Object.entries(user.cartes ?? {}).sort(
    ([a], [b]) => parseInt(b, 10) - parseInt(a, 10),
  );
  const years = [
    ...new Set([
      ...yearOptions().map((year) => year.split("-")[0]),
      ...cards.map(([year]) => year),
    ]),
  ].sort();

  useEffect(() => {
    const dialog = dialogRef.current!;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.showModal();
    titleRef.current?.focus();
    // Safari's keyboard resizes the visual viewport, not necessarily the layout viewport.
    const viewport = window.visualViewport;
    const resize = () => {
      dialog.style.setProperty(
        "--visible-height",
        `${viewport?.height ?? window.innerHeight}px`,
      );
      dialog.style.setProperty(
        "--visible-top",
        `${viewport?.offsetTop ?? 0}px`,
      );
    };
    resize();
    viewport?.addEventListener("resize", resize);
    viewport?.addEventListener("scroll", resize);
    return () => {
      viewport?.removeEventListener("resize", resize);
      viewport?.removeEventListener("scroll", resize);
      dialog.close();
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  useEffect(() => {
    if (mode === "view") titleRef.current?.focus();
    else formRef.current?.querySelector<HTMLElement>("input, select")?.focus();
  }, [mode]);
  useEffect(() => {
    if (confirmation) confirmCancelRef.current?.focus();
  }, [confirmation]);

  function changeMode(next: typeof mode) {
    setMessage(null);
    setConfirmation(null);
    setMode(next);
  }
  function close() {
    if (busyRef.current) return;
    if (mode !== "view") setConfirmation({ kind: "discard" });
    else onClose();
  }
  async function mutate(label: string, operation: () => Promise<void>) {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(label);
    setMessage(null);
    try {
      await operation();
    } catch (error) {
      setMessage({
        error: true,
        text:
          error instanceof Error
            ? error.message
            : "L’opération a échoué. Réessayez.",
      });
    } finally {
      busyRef.current = false;
      setBusy("");
    }
  }

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const nom = String(data.get("nom") ?? "").trim();
    const prenom = String(data.get("prenom") ?? "").trim();
    const identifiant = String(data.get("identifiant") ?? "").trim();
    const role = String(data.get("role") ?? "");
    const idChanged = identifiant !== (user.identifiant ?? "");
    if (!nom || !prenom || (idChanged && !/^\d{6}$/.test(identifiant))) {
      setMessage({
        error: true,
        text: "Renseignez le nom et le prénom. Un nouvel identifiant doit contenir exactement 6 chiffres.",
      });
      return;
    }
    void mutate("Enregistrement…", async () => {
      let updated = user;
      const identityChanged =
        nom !== user.nom || prenom !== user.prenom || idChanged;
      if (identityChanged) {
        // Unchanged email identifiers must not be sent to the member_id-only endpoint.
        await request(base, "PUT", {
          nom,
          prenom,
          ...(idChanged ? { identifiant } : {}),
        });
        updated = { ...user, nom, prenom, identifiant };
        onChange(updated);
      }
      if (role !== user.role) {
        try {
          await request(`${base}/role`, "PUT", { role });
        } catch (error) {
          throw new Error(
            `${identityChanged ? "Identité enregistrée, mais rôle non modifié. " : ""}${error instanceof Error ? error.message : "Réessayez."}`,
          );
        }
        onChange({ ...updated, role });
      }
      setMode("view");
      setMessage({ error: false, text: "Modifications enregistrées." });
    });
  }

  function saveCard(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const prefix = String(data.get("prefix"));
    const rawNum = String(data.get("num") ?? "").trim();
    if (!PREFIXES.includes(prefix)) {
      setMessage({ error: true, text: "Choisissez un préfixe valide." });
      return;
    }

    let code = "";
    if (rawNum) {
      const num = Number(rawNum);
      if (!Number.isSafeInteger(num) || num < 1) {
        setMessage({
          error: true,
          text: "Le numéro doit être un entier supérieur ou égal à 1.",
        });
        return;
      }
      code = `${prefix}-${num}`;
    }

    const replacing = !!user.cartes?.[cardYear];
    void mutate(replacing ? "Mise à jour…" : "Ajout…", async () => {
      const response = await request(`${base}/annees`, "PUT", {
        annee: academicYear(cardYear),
        prefix,
        ...(code ? { annee_code: code } : {}),
      });
      const result = await response.json();
      const assignedCode = result.annee_code;
      onChange({ ...user, cartes: { ...user.cartes, [cardYear]: assignedCode } });
      setMode("view");
      setMessage({
        error: false,
        text: `Carte ${assignedCode} ${replacing ? "mise à jour" : "ajoutée"} pour ${academicYear(cardYear)}.`,
      });
    });
  }

  function confirm() {
    if (!confirmation) return;
    if (confirmation.kind === "discard") {
      onClose();
      return;
    }
    void mutate("Suppression…", async () => {
      if (confirmation.kind === "user") {
        await request(base, "DELETE");
        onDelete();
      } else if (confirmation.kind === "card") {
        await request(
          `${base}/annees/${encodeURIComponent(confirmation.year)}`,
          "DELETE",
        );
        const cartes = { ...user.cartes };
        delete cartes[confirmation.year];
        onChange({ ...user, cartes });
        setConfirmation(null);
        setMessage({ error: false, text: "Carte supprimée." });
        titleRef.current?.focus();
      }
    });
  }

  function openCard(year = String(currentYear()), code = "") {
    setCardYear(year);
    setCardCode(code);
    changeMode("card");
  }

  return (
    <dialog
      ref={dialogRef}
      className="admin-user-dialog admin-users"
      aria-labelledby="user-title"
      onKeyDown={(event) => {
        if (event.key !== "Tab") return;
        const controls = Array.from(
          event.currentTarget.querySelectorAll<HTMLElement>(
            "button:not(:disabled), input:not(:disabled), select:not(:disabled)",
          ),
        ).filter((element) => element.getClientRects().length);
        const first = controls[0],
          last = controls[controls.length - 1];
        if (!first) {
          event.preventDefault();
          return;
        }
        if (
          event.shiftKey &&
          (document.activeElement === first ||
            !controls.includes(document.activeElement as HTMLElement))
        ) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }}
      onCancel={(event) => {
        event.preventDefault();
        if (!busyRef.current) {
          if (confirmation) {
            setConfirmation(null);
            titleRef.current?.focus();
          } else close();
        }
      }}
    >
      <div className="flex h-full min-h-0 flex-col">
        <header className="flex shrink-0 items-center justify-between gap-2 border-b border-slate-200 px-4 py-3 sm:px-6">
          <div className="min-w-0">
            <p className="text-xs font-medium text-blue-700">
              {mode === "edit"
                ? "Modifier le profil"
                : mode === "card"
                  ? "Gérer une carte"
                  : "Fiche utilisateur"}
            </p>
            <h2
              ref={titleRef}
              tabIndex={-1}
              id="user-title"
              className="truncate text-lg font-semibold text-blue-900"
            >
              {user.prenom} {user.nom}
            </h2>
          </div>
          <button
            type="button"
            className="admin-button admin-secondary shrink-0 text-sm"
            disabled={!!busy}
            onClick={close}
            aria-label="Fermer la fiche utilisateur"
          >
            Fermer
          </button>
        </header>
        <div
          className="min-h-0 flex-1 space-y-6 overflow-y-auto overscroll-contain p-4 sm:p-6"
          aria-busy={!!busy}
        >
          {mode === "edit" ? (
            <form ref={formRef} id="user-edit" onSubmit={save}>
              <fieldset
                disabled={!!busy || !!confirmation}
                className="space-y-4"
              >
                <legend className="sr-only">
                  Modifier les informations de l’utilisateur
                </legend>
                <label className="admin-label">
                  Nom
                  <input
                    className="admin-input"
                    name="nom"
                    autoComplete="family-name"
                    defaultValue={user.nom}
                    required
                  />
                </label>
                <label className="admin-label">
                  Prénom
                  <input
                    className="admin-input"
                    name="prenom"
                    autoComplete="given-name"
                    defaultValue={user.prenom}
                    required
                  />
                </label>
                <label className="admin-label">
                  Identifiant
                  <input
                    className="admin-input"
                    name="identifiant"
                    defaultValue={user.identifiant ?? ""}
                    autoCapitalize="none"
                    autoComplete="off"
                    spellCheck={false}
                    inputMode={
                      user.identifiant?.includes("@") ? "email" : "numeric"
                    }
                    aria-describedby="identifier-help"
                  />
                </label>
                <p id="identifier-help" className="text-xs text-slate-600">
                  Pour changer l’identifiant, saisissez un matricule à 6
                  chiffres. Une adresse email existante peut être conservée.
                </p>
                <label className="admin-label">
                  Rôle
                  <select
                    className="admin-input"
                    name="role"
                    defaultValue={user.role}
                  >
                    {ROLES.map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <p className="text-sm text-slate-600">
                  Tous les changements sont appliqués avec « Enregistrer ».
                </p>
              </fieldset>
            </form>
          ) : mode === "card" ? (
            <form ref={formRef} id="user-card" onSubmit={saveCard}>
              <fieldset
                disabled={!!busy || !!confirmation}
                className="space-y-4"
              >
                <legend className="mb-4 font-semibold text-blue-900">
                  {user.cartes?.[cardYear]
                    ? "Modifier une carte"
                    : "Ajouter une carte"}
                </legend>
                <label className="admin-label">
                  Année académique
                  <select
                    name="annee"
                    className="admin-input"
                    value={cardYear}
                    onChange={(event) => setCardYear(event.target.value)}
                  >
                    {years.map((year) => (
                      <option value={year} key={year}>
                        {academicYear(year)}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="grid grid-cols-2 gap-3">
                  <label className="admin-label">
                    Préfixe
                    <select
                      className="admin-input"
                      name="prefix"
                      defaultValue={cardCode ? cardCode.split("-")[0] : "A"}
                    >
                      {PREFIXES.map((prefix) => (
                        <option key={prefix}>{prefix}</option>
                      ))}
                    </select>
                  </label>
                  <label className="admin-label">
                    Numéro
                    <input
                      className="admin-input"
                      name="num"
                      type="number"
                      inputMode="numeric"
                      min={1}
                      step={1}
                      max={Number.MAX_SAFE_INTEGER}
                      defaultValue={cardCode ? cardCode.split("-")[1] : ""}
                      placeholder="Automatique"
                    />
                    <span className="text-xs text-slate-500">
                      Laissez vide pour attribuer le premier numéro disponible.
                    </span>
                  </label>
                </div>
                {user.cartes?.[cardYear] && (
                  <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">
                    La carte {user.cartes[cardYear]} sera remplacée pour{" "}
                    {academicYear(cardYear)}.
                  </p>
                )}
              </fieldset>
            </form>
          ) : (
            <>
              <section aria-labelledby="profile-heading">
                <h3
                  id="profile-heading"
                  className="mb-3 font-semibold text-blue-900"
                >
                  Informations utilisateur
                </h3>
                <dl className="grid grid-cols-2 gap-4 rounded-2xl bg-slate-50 p-4 text-sm">
                  <div className="min-w-0">
                    <dt className="text-slate-500">Prénom</dt>
                    <dd className="break-words font-medium">{user.prenom}</dd>
                  </div>
                  <div className="min-w-0">
                    <dt className="text-slate-500">Nom</dt>
                    <dd className="break-words font-medium">{user.nom}</dd>
                  </div>
                  <div className="col-span-2">
                    <dt className="text-slate-500">Identifiant</dt>
                    <dd className="break-all font-medium">
                      {user.identifiant || "Sans identifiant"}
                    </dd>
                  </div>
                  <div className="col-span-2">
                    <dt className="mb-1 text-slate-500">Rôle</dt>
                    <dd>
                      <span className="admin-badge">
                        {roleLabel(user.role)}
                      </span>
                    </dd>
                  </div>
                </dl>
              </section>
              <section aria-labelledby="cards-heading" className="space-y-3">
                <h3 id="cards-heading" className="font-semibold text-blue-900">
                  Cartes{" "}
                  <span className="text-slate-500">({cards.length})</span>
                </h3>
                {cards.length ? (
                  <ul className="space-y-2">
                    {cards.map(([year, code]) => (
                      <li
                        key={year}
                        className="rounded-xl border border-slate-200 p-3"
                      >
                        <div className="flex flex-wrap justify-between gap-2 text-sm">
                          <span>{academicYear(year)}</span>
                          <strong>{code}</strong>
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          <button
                            className="admin-button admin-secondary text-sm"
                            disabled={!!busy || !!confirmation}
                            onClick={() => openCard(year, code)}
                            aria-label={`Modifier la carte ${code} de ${academicYear(year)}`}
                          >
                            Modifier
                          </button>
                          <button
                            className="admin-button text-sm text-red-700"
                            disabled={!!busy || !!confirmation}
                            onClick={() => {
                              setMessage(null);
                              setConfirmation({ kind: "card", year });
                            }}
                            aria-label={`Supprimer la carte ${code} de ${academicYear(year)}`}
                          >
                            Supprimer
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-slate-500">
                    Aucune carte pour cet utilisateur.
                  </p>
                )}
                <button
                  className="admin-button admin-secondary w-full"
                  disabled={!!busy || !!confirmation}
                  onClick={() => openCard()}
                >
                  + Ajouter une carte
                </button>
              </section>
              <section
                aria-labelledby="danger-heading"
                className="rounded-2xl border border-red-200 p-4"
              >
                <h3 id="danger-heading" className="font-semibold text-red-800">
                  Zone dangereuse
                </h3>
                <p className="mt-2 text-sm text-slate-600">
                  La suppression du compte et de ses cartes est définitive.
                </p>
                <button
                  className="admin-button mt-2 text-left text-sm text-red-700"
                  disabled={!!busy || !!confirmation}
                  onClick={() => {
                    setMessage(null);
                    setConfirmation({ kind: "user" });
                  }}
                >
                  Supprimer l’utilisateur
                </button>
              </section>
            </>
          )}
        </div>
        <footer className="admin-dialog-actions shrink-0 space-y-3 border-t border-slate-200 bg-white px-4 pt-3 sm:px-6">
          {message && (
            <p
              role={message.error ? "alert" : "status"}
              className={`${message.error ? "admin-error" : "admin-success"} max-h-24 overflow-y-auto text-sm`}
            >
              {message.text}
            </p>
          )}
          {confirmation ? (
            <div
              role="group"
              aria-labelledby="confirm-description"
              className="space-y-3"
            >
              <p
                id="confirm-description"
                className="text-sm font-medium text-slate-800"
              >
                {confirmation.kind === "discard"
                  ? "Fermer sans enregistrer les changements ?"
                  : confirmation.kind === "user"
                    ? `Supprimer définitivement ${user.prenom} ${user.nom} et ses cartes ?`
                    : `Supprimer la carte ${academicYear(confirmation.year)} ?`}
              </p>
              <div className="grid grid-cols-2 gap-2">
                <button
                  ref={confirmCancelRef}
                  className="admin-button admin-secondary"
                  disabled={!!busy}
                  onClick={() => {
                    setConfirmation(null);
                    titleRef.current?.focus();
                  }}
                >
                  Annuler
                </button>
                <button
                  className="admin-button bg-red-700 text-white hover:bg-red-800"
                  disabled={!!busy}
                  onClick={confirm}
                >
                  {busy ||
                    (confirmation.kind === "discard" ? "Fermer" : "Supprimer")}
                </button>
              </div>
            </div>
          ) : mode !== "view" ? (
            <div className="grid grid-cols-[auto_1fr] gap-2">
              <button
                className="admin-button admin-secondary"
                disabled={!!busy}
                onClick={() => changeMode("view")}
              >
                Annuler
              </button>
              <button
                className="admin-button admin-primary"
                type="submit"
                form={mode === "edit" ? "user-edit" : "user-card"}
                disabled={!!busy}
              >
                {busy ||
                  (mode === "edit"
                    ? "Enregistrer"
                    : user.cartes?.[cardYear]
                      ? "Mettre à jour la carte"
                      : "Ajouter la carte")}
              </button>
            </div>
          ) : (
            <button
              className="admin-button admin-primary w-full"
              onClick={() => changeMode("edit")}
            >
              Modifier le profil
            </button>
          )}
        </footer>
      </div>
    </dialog>
  );
}
