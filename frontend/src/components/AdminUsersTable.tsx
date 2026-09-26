import { useEffect, useMemo, useRef, useState } from "react";
import UserDetails from "./UserDetails";
import {
  filterUsers,
  request,
  ROLES,
  roleLabel,
  type User,
} from "../lib/admin-users";

export default function AdminUsersTable() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [query, setQuery] = useState("");
  const [role, setRole] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/me", { credentials: "include" });
      if (response.status === 401) {
        window.location.href = "/login";
        return;
      }
      if (!response.ok)
        throw new Error("Impossible de vérifier vos droits. Réessayez.");
      const me = await response.json();
      if (me.role !== "admin") {
        window.location.href = "/";
        return;
      }
      setUsers(await (await request("/api/admin/users")).json());
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Impossible de charger les utilisateurs.",
      );
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void load();
  }, []);

  const filtered = useMemo(
    () => filterUsers(users, query, role),
    [users, query, role],
  );
  const selected = users.find((user) => user.id === selectedId);
  const totalCards = users.reduce(
    (sum, user) => sum + Object.keys(user.cartes ?? {}).length,
    0,
  );
  function open(user: User, trigger: HTMLButtonElement) {
    triggerRef.current = trigger;
    setNotice("");
    setSelectedId(user.id);
  }
  function close() {
    setSelectedId(null);
    requestAnimationFrame(() => {
      const trigger = triggerRef.current;
      if (trigger?.isConnected && trigger.getClientRects().length)
        trigger.focus();
      else searchRef.current?.focus();
    });
  }
  const downloadExcel = () => {
    if (!users.length) return;
    const yearSet = new Set<string>();
    users.forEach((u) => {
      Object.keys(u.cartes ?? {}).forEach((year) => yearSet.add(year));
    });
    const yearColumns = Array.from(yearSet).sort((a, b) => {
      const numA = parseInt(a, 10);
      const numB = parseInt(b, 10);
      if (!Number.isNaN(numA) && !Number.isNaN(numB)) return numB - numA;
      if (!Number.isNaN(numA)) return -1;
      if (!Number.isNaN(numB)) return 1;
      return b.localeCompare(a);
    });
    const header = ["Nom", "Prénom", "Identifiant", "Rôle", ...yearColumns];
    const rows = users.map((u) => [
      u.nom,
      u.prenom,
      u.identifiant ?? "",
      u.role,
      ...yearColumns.map((year) => u.cartes?.[year] ?? ""),
    ]);
    const escapeCell = (value: string) => `"${value.replace(/"/g, '""')}"`;
    const tableContent = [header, ...rows]
      .map((row) => row.map((cell) => escapeCell(String(cell ?? ""))).join(";"))
      .join("\n");
    const blob = new Blob(["\uFEFF" + tableContent], {
      type: "application/vnd.ms-excel;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `utilisateurs-${new Date().toISOString().split("T")[0]}.xls`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(() => URL.revokeObjectURL(url), 0);
  };

  return (
    <div className="admin-users grid min-w-0 gap-4">
      <section
        className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6"
        aria-labelledby="users-title"
      >
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs font-semibold uppercase tracking-widest text-blue-700">
            Espace admin
          </p>
          <button
            type="button"
            className="admin-button admin-secondary shrink-0 text-sm"
            onClick={downloadExcel}
            disabled={loading || !!error || !users.length}
            aria-label="Exporter en Excel"
          >
            <span className="sm:hidden">Export Excel</span>
            <span className="hidden sm:inline">Exporter en Excel</span>
          </button>
        </div>
        <h1
          id="users-title"
          className="mt-2 text-xl font-semibold text-blue-900 sm:text-3xl"
        >
          Gestion des utilisateurs
        </h1>
        <p className="mt-1 text-sm text-slate-600">
          Retrouvez et gérez les profils, rôles et cartes.
        </p>
        {!loading && !error && (
          <div className="mt-3 flex flex-wrap gap-2 text-xs sm:text-sm">
            <span className="rounded-full bg-blue-50 px-3 py-1 text-blue-900">
              <strong>{users.length}</strong> utilisateurs
            </span>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-700">
              <strong>{totalCards}</strong> cartes
            </span>
            <span className="hidden rounded-full bg-amber-50 px-3 py-1 text-amber-900 sm:inline-block">
              <strong>
                {users.filter((user) => user.role === "en attente").length}
              </strong>{" "}
              en attente
            </span>
          </div>
        )}
        <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_12rem]">
          <label className="admin-label">
            Rechercher un utilisateur
            <input
              ref={searchRef}
              className="admin-input"
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Nom, prénom ou identifiant"
              autoComplete="off"
            />
          </label>
          <label className="admin-label flex items-center gap-3 sm:block">
            Rôle
            <select
              className="admin-input mt-0 flex-1 sm:mt-2"
              value={role}
              onChange={(event) => setRole(event.target.value)}
            >
              <option value="">Tous</option>
              {ROLES.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </section>
      {notice && (
        <p role="status" className="admin-success">
          {notice}
        </p>
      )}
      {loading ? (
        <p role="status" className="rounded-2xl bg-white p-6 text-slate-600">
          Chargement des utilisateurs…
        </p>
      ) : error ? (
        <div className="admin-error" role="alert">
          <p>{error}</p>
          <button
            className="admin-button admin-secondary mt-3"
            onClick={() => void load()}
          >
            Réessayer
          </button>
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm text-slate-600" role="status">
              {filtered.length} utilisateurs affichés sur {users.length}
            </p>
            {(query || role) && (
              <button
                className="admin-button text-sm text-blue-900"
                onClick={() => {
                  setQuery("");
                  setRole("");
                  searchRef.current?.focus();
                }}
              >
                Effacer les filtres
              </button>
            )}
          </div>
          {!filtered.length ? (
            <p className="rounded-2xl border border-dashed border-slate-300 bg-white p-6 text-slate-600">
              {users.length
                ? "Aucun utilisateur ne correspond à cette recherche."
                : "Aucun utilisateur pour le moment."}
            </p>
          ) : (
            <>
              <ul className="space-y-2 md:hidden" aria-label="Utilisateurs">
                {filtered.map((user) => (
                  <li key={user.id}>
                    <button
                      type="button"
                      className="flex w-full items-center gap-3 rounded-2xl border border-slate-200 bg-white p-3 text-left shadow-sm hover:border-blue-300"
                      onClick={(event) => open(user, event.currentTarget)}
                      aria-haspopup="dialog"
                      aria-label={`Ouvrir la fiche de ${user.prenom} ${user.nom}`}
                    >
                      <span className="min-w-0 flex-1">
                        <span className="block break-words font-semibold text-slate-900">
                          {user.prenom} {user.nom}
                        </span>
                        <span className="block break-all text-sm text-slate-500">
                          {user.identifiant || "Sans identifiant"}
                        </span>
                        <span className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                          <span className="admin-badge">
                            {roleLabel(user.role)}
                          </span>
                          <span className="text-slate-600">
                            {Object.keys(user.cartes ?? {}).length} carte(s)
                          </span>
                        </span>
                      </span>
                      <span
                        aria-hidden="true"
                        className="text-xl text-blue-900"
                      >
                        ›
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
              <div className="hidden min-w-0 overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm md:block">
                <table className="w-full text-left text-sm">
                  <caption className="sr-only">
                    Utilisateurs et accès à leur fiche de gestion
                  </caption>
                  <thead className="bg-slate-50 text-slate-600">
                    <tr>
                      {[
                        "Nom",
                        "Prénom",
                        "Identifiant",
                        "Rôle",
                        "Cartes",
                        "Actions",
                      ].map((label) => (
                        <th
                          scope="col"
                          key={label}
                          className="whitespace-nowrap px-4 py-3 font-semibold"
                        >
                          {label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filtered.map((user) => (
                      <tr key={user.id} className="hover:bg-blue-50/40">
                        <td className="px-4 py-2 font-medium">{user.nom}</td>
                        <td className="px-4 py-2">{user.prenom}</td>
                        <td className="max-w-xs break-all px-4 py-2">
                          {user.identifiant || "—"}
                        </td>
                        <td className="whitespace-nowrap px-4 py-2">
                          <span className="admin-badge">
                            {roleLabel(user.role)}
                          </span>
                        </td>
                        <td className="px-4 py-2">
                          {Object.keys(user.cartes ?? {}).length}
                        </td>
                        <td className="whitespace-nowrap px-4 py-2">
                          <button
                            className="admin-button admin-secondary"
                            onClick={(event) => open(user, event.currentTarget)}
                            aria-haspopup="dialog"
                            aria-label={`Gérer ${user.prenom} ${user.nom}`}
                          >
                            Gérer
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
      {selected && (
        <UserDetails
          key={selected.id}
          user={selected}
          onClose={close}
          onChange={(updated) =>
            setUsers((previous) =>
              previous.map((user) => (user.id === updated.id ? updated : user)),
            )
          }
          onDelete={() => {
            setUsers((previous) =>
              previous.filter((user) => user.id !== selected.id),
            );
            setNotice("Utilisateur supprimé.");
            close();
          }}
        />
      )}
    </div>
  );
}
