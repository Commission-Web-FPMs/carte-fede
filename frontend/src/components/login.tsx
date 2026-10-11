import React, { useEffect, useState } from "react";

interface LoginFormProps {
  next?: string;
}

const isSixDigits = (value: string) => /^\d{6}$/.test(value.trim());
const isEmail = (value: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());

const LoginForm: React.FC<LoginFormProps> = ({ next = "/" }) => {
  const [oidc, setOidc] = useState<boolean | null>(null);
  useEffect(() => {
    fetch("/api/auth/mode", { credentials: "include" }).then(r => r.ok ? r.json() : null)
      .then(d => {
        if (!d) throw new Error("Mode indisponible");
        setOidc(d.mode === "oidc");
        if (d.mode === "oidc") window.location.replace("/api/auth/oidc/login");
      }).catch(() => setError("Connexion indisponible. Réessayez plus tard."));
  }, []);
  const [ident, setIdent] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError("");

    const trimmedIdent = ident.trim();
    if (!trimmedIdent || !password) {
      setError("Identifiant et mot de passe requis.");
      return;
    }

    const payload: {
      password: string;
      remember: boolean;
      email?: string;
      identifiant?: string;
    } = { password, remember };
    if (isEmail(trimmedIdent)) {
      payload.email = trimmedIdent.toLowerCase();
    } else if (isSixDigits(trimmedIdent)) {
      payload.identifiant = trimmedIdent;
    } else {
      setError("Saisis un email valide.");
      return;
    }

    try {
      setIsLoading(true);
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        let data: any = {};
        try {
          data = await res.json();
        } catch (err) {
          console.error(err);
        }
        setError(data.error || `Erreur ${res.status}`);
        return;
      }

      window.location.href = next || "/";
    } catch (err) {
      console.error(err);
      setError("Erreur réseau, réessaie plus tard.");
    } finally {
      setIsLoading(false);
    }
  };

  if (oidc === null) return <p role="status">{error || "Chargement…"}</p>;
  if (oidc) return <section className="rounded-xl bg-white p-6 shadow">
    <p className="mb-4">Redirection vers Authentik…</p>
    <a className="rounded bg-blue-700 px-4 py-2 text-white" href="/api/auth/oidc/login">Connexion Authentik DEV</a>
  </section>;
  return (
    <div className="w-full max-w-md rounded-xl bg-white px-5 py-6 shadow-lg sm:px-8">
      <h1 className="mb-2 bg-white text-xl font-semibold text-bleu sm:text-2xl">Connexion</h1>
      <form onSubmit={handleSubmit} className="stack" noValidate>
        <label htmlFor="ident">Identifiant (email ou matricule UMONS)</label>
        <input
          id="ident"
          name="ident"
          type="text"
          placeholder="email ou matricule UMONS"
          autoComplete="username"
          value={ident}
          onChange={(e) => setIdent(e.target.value)}
          className="border border-gray-300 rounded-lg p-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          required
        />

        <label htmlFor="password">Mot de passe</label>
        <div className="password-field">
          <input
            id="password"
            name="password"
            type="password"
            placeholder="••••••••"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="password-input border border-gray-300 rounded-lg p-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            required
          />
          <button
            type="button"
            className="password-toggle"
            data-password-toggle
            aria-label="Afficher le mot de passe"
            aria-pressed="false"
          >
            <svg className="icon-show" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
              <path
                d="M1.5 12s3.5-6 10.5-6 10.5 6 10.5 6-3.5 6-10.5 6S1.5 12 1.5 12Z"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" strokeWidth="1.8" />
            </svg>
            <svg className="icon-hide" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
              <path
                d="M3 3l18 18"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
              />
              <path
                d="M10.6 6.3A11.3 11.3 0 0 1 12 6c7 0 10.5 6 10.5 6a18.5 18.5 0 0 1-3.2 3.8M6.7 6.7C3.5 8.7 1.5 12 1.5 12s3.5 6 10.5 6c1.8 0 3.4-.4 4.8-1"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        </div>

        <label className="remember-row">
          <input
            type="checkbox"
            checked={remember}
            onChange={(e) => setRemember(e.target.checked)}
          />
          <span>Se souvenir de moi</span>
        </label>

        <button
          type="submit"
          disabled={isLoading}
          className="rounded-lg border-2 border-blue-900 bg-blue-900 px-4 py-2 text-white transition duration-150 hover:bg-blue-50 hover:text-blue-50 disabled:opacity-60 disabled:cursor-not-allowed"
        >

          {isLoading ? "Connexion..." : "Se connecter"}
        </button>

        <p aria-live="polite" style={{ color: "#b00" }}>
          {error}
        </p>

        <style>
          {`
            .stack { display:flex; flex-direction:column; gap:.8rem; max-width:380px; }
            input, button { padding:.55rem .7rem; font-size:1rem; }
            .remember-row { display:flex; align-items:center; gap:.5rem; font-size:.95rem; }
            .remember-row input { width:auto; padding:0; }
          `}
        </style>
      </form>
      <a href="/RequestPasswordReset" className="text-sm text-gray-600 hover:underline">
        Mot de passe oublié ?
      </a>
    </div>
  );
};

export default LoginForm;
