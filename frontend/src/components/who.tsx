// src/components/Nav.tsx
import { useState, useEffect } from "react";
import { fetchCurrentUser } from "../lib/current-user";
import { navItems, type NavItem } from "./NavItems";

type Me = {
  email?: string;
  role?: string;
};

export default function Nav() {
  const [role, setRole] = useState<string>("guest");
  const [me, setMe] = useState<Me | null>(null);

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

  return (
    <nav className="container mx-auto flex justify-between items-center gap-4 p-4">
      {/* Liens du menu */}
      <ul className="flex flex-wrap gap-4 text-sm lg:text-base">
        {navItems.map((item: NavItem) => {
          if (item.adminOnly && role !== "admin") return null;
          return (
            <li key={item.href}>
              <a
                href={item.href}
                className="relative px-1 py-1 after:absolute after:bottom-0 after:left-0 after:h-[3px] after:w-0 after:rounded-full after:bg-blue-900 after:duration-500 hover:after:w-full"
              >
                {item.label}
              </a>
            </li>
          );
        })}
      </ul>

      {/* Partie droite (utilisateur connecté ou invité) */}
      <div className="text-sm text-gray-700">
        {me ? (
          <span>
            Connecté : <strong>{me.email || me.role}</strong> ({me.role})
          </span>
        ) : (
          <span className="text-gray-500">Non connecté</span>
        )}
      </div>
    </nav>
  );
}
