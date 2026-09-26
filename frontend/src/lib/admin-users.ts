export type User = {
  id: number;
  nom: string;
  prenom: string;
  identifiant?: string | null;
  cartes?: Record<string, string>;
  role: string;
};

export const ROLES = [
  ["en attente", "En attente"],
  ["member", "Member"],
  ["verifier", "Verifier"],
  ["admin", "Admin"],
] as const;
export const PREFIXES = ["A", "F", "E", "EA", "MI", "S"];
export const roleLabel = (role: string) =>
  ROLES.find(([value]) => value === role)?.[1] ?? role;
export const academicYear = (year: string) =>
  `${parseInt(year, 10)}-${parseInt(year, 10) + 1}`;
export function currentYear() {
  const now = new Date();
  return now.getFullYear() - (now.getMonth() < 8 ? 1 : 0);
}
export const yearOptions = () =>
  Array.from({ length: 9 }, (_, i) =>
    academicYear(String(currentYear() - 2 + i)),
  );
const normalize = (value: string) =>
  value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("fr");
export function filterUsers(users: User[], query: string, role: string) {
  const terms = normalize(query).trim().split(/\s+/).filter(Boolean);
  return users.filter(
    (user) =>
      (!role || user.role === role) &&
      terms.every((term) =>
        normalize(
          `${user.nom} ${user.prenom} ${user.identifiant ?? ""}`,
        ).includes(term),
      ),
  );
}

export async function request(
  path: string,
  method = "GET",
  body?: object,
): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      credentials: "include",
      ...(body
        ? {
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          }
        : {}),
    });
  } catch {
    throw new Error(
      "Connexion impossible. Vérifiez votre connexion puis réessayez.",
    );
  }
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    const fallback =
      response.status === 401
        ? "Session expirée. Reconnectez-vous."
        : response.status === 403
          ? "Vous n’avez pas les droits nécessaires."
          : `L’opération a échoué (erreur ${response.status}). Réessayez.`;
    throw new Error(
      typeof data?.error === "string" && ![401, 403].includes(response.status)
        ? data.error
        : fallback,
    );
  }
  return response;
}
