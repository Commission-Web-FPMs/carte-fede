import { useEffect, useState } from "react";
import { fetchCurrentUser } from "../lib/current-user";

type Membership = { annee: number; annee_code?: string };

export default function MembershipTable() {
  const [data, setData] = useState<Membership[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      const me = await fetchCurrentUser();
      if (!me.ok) return (window.location.href = "/login?next=" + encodeURIComponent(window.location.pathname));

      const res = await fetch("/api/memberships", { credentials: "include" });
      if (!res.ok) return setData([]);
      const json = await res.json();
      setData(Array.isArray(json) ? json.sort((a, b) => b.annee - a.annee) : []);
      setLoading(false);
    };
    fetchData();
  }, []);

  if (loading) return <p>Chargement des cartes...</p>;
  if (!data.length) return <p>Aucune carte</p>;

  return (
    <table className="w-full border-collapse">
      <thead>
        <tr><th>Année</th><th>Numéro</th></tr>
      </thead>
      <tbody>
        {data.map(x => (
          <tr key={x.annee}>
            <td className="border px-2 py-1">{x.annee}-{x.annee+1}</td>
            <td className="border px-2 py-1">{x.annee_code ?? ''}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
