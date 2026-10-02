import { useState, useEffect, useRef } from "react";
import { fetchCurrentUser } from "../lib/current-user";
import { navItems as originalNavItems, type NavItem } from "./NavItems";

type Me = {
  email?: string;
  role?: string;
  member_id?: string;
  identifiant?: string;  // 🔹 ajouté
};


export default function Nav() {
  const [role, setRole] = useState<string>("guest");
  const [me, setMe] = useState<Me | null>(null);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const close = () => setIsMenuOpen(false);
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && isMenuOpen) { close(); menuButton.current?.focus(); }
    };
    document.addEventListener("keydown", escape);
    document.addEventListener("astro:before-swap", close);
    return () => {
      document.removeEventListener("keydown", escape);
      document.removeEventListener("astro:before-swap", close);
    };
  }, [isMenuOpen]);

  useEffect(() => {
    fetchCurrentUser()
      .then(async (res) => {
        if (!res.ok) {
          setRole("guest");
          setMe(null);
          return;
        }
        const data = await res.json();
        setRole(data.role || "guest");
        setMe(data);
      })
      .catch(() => {
        setRole("guest");
        setMe(null);
      });
  }, []);

  useEffect(() => {
    const onResize = () => {
      if (window.innerWidth >= 1024) {
        setIsMenuOpen(false);
      }
    };

    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const handleLogout = async () => {
    await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
    setRole("guest");
    setMe(null);
    // Optionnel : reload de la page pour forcer la redirection
    window.location.href = "/";
  };

  // Filtrer les items selon la connexion
  const navItems = originalNavItems.filter((item) => {
    if (item.adminOnly && role !== "admin") {
      if (!(item.verifierOnly && role === "verifier")) return false;
    }
    if (me && (item.label === "Se connecter" || item.label === "S'inscrire")) return false;
    return true;
  });

  const userLabel = me
    ? `Connecté : ${me.identifiant ?? me.email ?? "Utilisateur"} (${me.role})`
    : "Non connecté";

  return (
    <nav className="container mx-auto px-3 pb-2 lg:px-4 lg:pb-4">
      <div className="hidden items-center justify-between gap-6 lg:flex">
        <ul className="flex flex-wrap gap-4 text-sm lg:text-base">
          {navItems.map((item: NavItem) => (
            <li key={item.href} className="inline-flex">
              {item.label === "Site Fédé" ? (
                <a
                  href={item.href}
                  className="rounded-lg border-2 border-blue-900 bg-blue-900 px-4 py-2 text-white transition duration-150 hover:bg-blue-50 hover:text-blue-900"
                >
                  {item.label}
                </a>
              ) : (
                <a
                  href={item.href}
                  className="relative px-1 py-1 after:absolute after:bottom-0 after:left-0 after:h-[3px] after:w-0 after:rounded-full after:bg-blue-900 after:duration-500 hover:after:w-full"
                >
                  {item.label}
                </a>
              )}
            </li>
          ))}
        </ul>

        <div className="text-sm text-gray-700 whitespace-nowrap text-right">
          <span className={me ? "" : "text-gray-500"}>{userLabel}</span>

          {me ? (
            <div className="mt-2">
              <button
                onClick={handleLogout}
                className="relative text-red-700 after:absolute after:bottom-0 after:left-0 after:h-[3px] after:w-0 after:rounded-full after:bg-red-700 after:duration-500 hover:after:w-full"
              >
                Se déconnecter
              </button>
            </div>
          ) : null}
        </div>
      </div>

      <div className="lg:hidden">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p title={userLabel} className={`truncate text-xs ${me ? "text-slate-700" : "text-slate-500"}`}>{userLabel}</p>
          </div>

          <button
            type="button"
            onClick={() => setIsMenuOpen((open) => !open)}
            ref={menuButton}
            aria-label={isMenuOpen ? "Fermer le menu" : "Ouvrir le menu"}
            aria-expanded={isMenuOpen}
            aria-controls="mobile-nav-panel"
            className="inline-flex min-h-11 shrink-0 items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-semibold text-blue-900 shadow-sm"
          >
            <span>Menu</span>
            <span aria-hidden="true" className="text-lg leading-none">
              {isMenuOpen ? "x" : "≡"}
            </span>
          </button>
        </div>

        {isMenuOpen ? (
          <div
            id="mobile-nav-panel"
            className="mt-2 max-h-[calc(100dvh-7rem)] overflow-y-auto overscroll-contain rounded-2xl border border-slate-200 bg-white p-3 shadow-xl shadow-slate-200/70 ring-1 ring-slate-100"
          >
            <p className="mb-3 break-all px-3 text-sm font-normal text-slate-600">{userLabel}</p>
            <ul className="space-y-1">
              {navItems.map((item: NavItem) => (
                <li key={item.href}>
                  <a
                    href={item.href}
                    onClick={() => setIsMenuOpen(false)}
                    className={
                      item.label === "Site Fédé"
                        ? "block rounded-2xl bg-blue-900 px-4 py-3 text-sm font-semibold text-white"
                        : "block rounded-2xl px-4 py-3 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
                    }
                  >
                    {item.label}
                  </a>
                </li>
              ))}
            </ul>

            {me ? (
              <div className="mt-3 border-t border-slate-100 pt-3">
                <button
                  type="button"
                  onClick={handleLogout}
                  className="block w-full rounded-2xl bg-rose-50 px-4 py-3 text-left text-sm font-semibold text-rose-700"
                >
                  Se déconnecter
                </button>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </nav>
  );
}
