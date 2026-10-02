export type NavItem = {
  label: string;
  href: string;
  adminOnly?: boolean;
  verifierOnly?: boolean;
};

export const navItems: NavItem[] = [
    { label: "Se connecter", href: "/login" },
    { label: "S'inscrire", href: "/register" },
    { label: "Mes cartes", href: "/cartes" },
    //{ label: "Générer mon QR", href: "/app/qr" },
    { label: "Changer de mot de passe", href:"/app/password" },
    { label: "Liste d'utilisateurs", href:"/admin/users", adminOnly: true },
    { label: "Admin", href: "/admin", adminOnly: true },
    { label: "Paramètres", href: "/admin/settings", adminOnly: true },
    { label : "Vérification", href: "/verif", adminOnly: true, verifierOnly: true },
    { label : "Site Fédé", href: "https://fede.fpms.ac.be" },
];
