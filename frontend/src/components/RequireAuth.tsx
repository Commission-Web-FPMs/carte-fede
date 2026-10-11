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

      try {
        const res = await fetchCurrentUser();

        if (!res.ok) {
          const mode = await fetch('/api/auth/mode', {credentials:'include'}).then(r => r.ok ? r.json() : null);
          window.location.href = mode?.mode === 'oidc' ? '/api/auth/oidc/login?expired=1' : redirectTo;
        } else {
          const data = await res.json();
          setAuthorized(true);
        }
      } catch (err) {
        window.location.href = redirectTo;
      } finally {
        setChecking(false);
      }
    };

    checkAuth();
  }, [redirectTo]);

  if (checking) {
    return <>{loader}</>;
  }

  if (!authorized) {
    return null;
  }

  return <>{children}</>;
}
