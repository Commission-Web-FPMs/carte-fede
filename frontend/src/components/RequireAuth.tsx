import { useEffect, useState } from "react";
import { fetchCurrentUser } from "../lib/current-user";

interface RequireAuthProps {
  children: React.ReactNode;
  redirectTo?: string; // URL de redirection si non connecté
  loader?: React.ReactNode; // Affichage pendant vérification
}

export default function RequireAuth({
  children,
  redirectTo = "/login",
  loader = <div>Chargement...</div>,
}: RequireAuthProps) {
  const [checking, setChecking] = useState(true);
  const [authorized, setAuthorized] = useState(false);

  useEffect(() => {
    const checkAuth = async () => {
      console.log("[RequireAuth] Début de la vérification d'authentification");

      try {
        const res = await fetchCurrentUser();
        console.log("[RequireAuth] Response status:", res.status);

        if (!res.ok) {
          console.warn("[RequireAuth] Non autorisé, redirection vers", redirectTo);
          window.location.href = redirectTo;
        } else {
          const data = await res.json();
          console.log("[RequireAuth] Connecté ! Données reçues :", data);
          setAuthorized(true);
        }
      } catch (err) {
        console.error("[RequireAuth] Erreur lors de la requête fetch :", err);
        window.location.href = redirectTo;
      } finally {
        console.log("[RequireAuth] Vérification terminée");
        setChecking(false);
      }
    };

    checkAuth();
  }, [redirectTo]);

  if (checking) {
    console.log("[RequireAuth] Toujours en vérification...");
    return <>{loader}</>;
  }

  if (!authorized) {
    console.log("[RequireAuth] Pas autorisé, mais la redirection devrait se produire");
    return null;
  }

  console.log("[RequireAuth] Autorisé, affichage des enfants");
  return <>{children}</>;
}
