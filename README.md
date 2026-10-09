# Carte Fédé

Application de gestion des comptes, des cartes annuelles et de leur vérification pour la Fédération des étudiants FPMs.

Les utilisateurs peuvent demander un compte, demander une carte, consulter leurs cartes et afficher un QR de vérification. Les administrateurs valident les demandes, confirment les paiements, attribuent les cartes et configurent les coordonnées de paiement.

## Organisation

| Dossier | Rôle |
| --- | --- |
| `backend/` | API Flask, modèles SQLAlchemy, migrations et scripts Python. Gunicorn écoute par défaut sur 8000. |
| `frontend/` | Pages Astro et composants React. Son Dockerfile construit le site et le sert avec Nginx sur 8080. |
| `nginx/` | Reverse proxy du Compose local uniquement, sur 80. Kubernetes utilise des HTTPRoutes. |
| `docs/` | Fonctionnement et procédures. |
| `.github/workflows/` | Publication des deux images et mise à jour des tags GitOps. |

Astro génère des fichiers statiques. Node intervient pendant la construction, puis Nginx sert les fichiers. Le navigateur utilise des chemins API relatifs `/api/...`, sur le même domaine que le site. Flask contrôle les droits et utilise des cookies de session.

## Lancement local

```bash
cp .env.example .env
# Renseigner SECRET_KEY dans .env, par exemple avec une valeur produite par openssl rand -hex 32.
docker compose up --build
```

Compose lance PostgreSQL, Flask, le frontend statique et un proxy Nginx local. Le site est sur `http://localhost` et l'API sur `http://localhost/api/`. Les trois services internes ne publient pas de port sur la machine hôte. Le volume `db_data` conserve la base.

L'exemple configure les cookies pour HTTP local. En HTTPS, utiliser `SESSION_COOKIE_SECURE=true` et `REMEMBER_COOKIE_SECURE=true`. Le backend exige `DATABASE_URL` et `SECRET_KEY` au démarrage.

Sur une base vide, activer temporairement `AUTO_CREATE_DB=1`, puis remettre la variable à `0`. Sur une base existante, appliquer les migrations dans l'ordre décrit dans [self-registration.md](docs/self-registration.md). Le démarrage ne les applique pas.

## Configuration et déploiement

Toute configuration applicative est fournie par variables d'environnement. Le chart accepte `env`, `envFrom` et `valueFrom`, avec des paramètres séparés pour le backend et le frontend. Aucun secret ne doit entrer dans la construction des images.

Le frontend reçoit uniquement des paramètres publics. `FRONTEND_BASE_URL` renseigne l'origine dans les pages, le sitemap et robots.txt au démarrage du conteneur. La même variable sert au backend pour les emails et les QR. Les images peuvent ainsi être réutilisées entre environnements sans reconstruire les URLs.

Les ports par défaut sont 8000 pour Flask et 8080 pour le frontend. Dans Helm, changer `containerPort` ou `frontend.containerPort` injecte automatiquement la variable `PORT` correspondante. Les ports des Services et le domaine de l'HTTPRoute sont des paramètres Helm.

À chaque push de branche, [build.yml](.github/workflows/build.yml) :

1. Construit et publie `ghcr.io/commission-web-fpms/carte-fede:<SHA>` depuis `backend/`.
2. Construit et publie `ghcr.io/commission-web-fpms/carte-fede-frontend:<SHA>` depuis `frontend/`.
3. Utilise la GitHub App pour sélectionner ou créer la branche correspondante dans [carte-fede-deployment](https://github.com/Commission-Web-FPMs/carte-fede-deployment).
4. Met à jour `image.tag` et `frontend.image.tag`, puis pousse un commit GitOps uniquement après les deux publications.

Le workflow ne lance pas Compose, n'applique pas les migrations et ne déploie pas directement dans Kubernetes. Une branche GitOps ne crée pas à elle seule un environnement.

Le chart adapté contient deux Deployments et deux Services. L'HTTPRoute envoie `/api` et ses sous-chemins ainsi que `/verify` exactement vers Flask, et les autres URLs vers le frontend. Le Gateway fournit TLS. PostgreSQL reste séparé.

Le détail est dans [architecture.md](docs/architecture.md) et dans le README du dépôt de déploiement.

## Vérifications disponibles

`backend/tests/test_requests.py` utilise une base PostgreSQL jetable et recrée ses tables. Son garde-fou exige une URL locale sur le port 15432. Fournir aussi `SECRET_KEY` et `AUTO_CREATE_DB=1`.

`frontend/scripts/` contient les vérifications du cache, des sessions, des requêtes, du chargement et de l'interface mobile. Certains scripts nécessitent Playwright et un site lancé séparément. `prepare-runtime.mjs` prépare les URLs publiques pendant la construction Docker ; ce n'est pas un test.

Le build frontend exécute `astro check` puis `astro build`. Il n'y a pas d'étape de test dédiée dans le workflow.

## Licence

Libre pour un usage personnel ou associatif. À compléter pour la redistribution.
