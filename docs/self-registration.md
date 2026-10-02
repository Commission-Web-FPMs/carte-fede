# Self-registration

## Objectif

Permettre aux nouveaux utilisateurs de créer eux-mêmes leur compte sur le site de la carte Fédé, sans nécessiter la création manuelle du compte par un administrateur.

## Flux

1. L'utilisateur accède à une page publique `/register/`.
2. Il renseigne :
   - prénom ;
   - nom ;
   - matricule UMONS ou adresse email pour une inscription non-UMONS ;
   - mot de passe ;
   - confirmation du mot de passe.
3. Le backend valide et normalise les données.
4. La demande est stockée dans `pending_registration` avec le mot de passe hashé. Elle expire après 30 jours et est supprimée lors des accès suivants à l'inscription ou à la file admin.
5. Aucune carte Fédé n'est attribuée automatiquement lors de l'inscription.
6. Un administrateur valide ou rejette la demande. La validation crée le compte membre, éventuellement avec une carte attribuée automatiquement dans la même transaction.
7. Les comptes existants peuvent demander une carte pour l'année actuelle ou suivante ; l'admin valide ou refuse, et l'utilisateur voit l'état de sa demande.

## Déploiement

La base de production n'utilise pas `db.create_all()` automatiquement. Avant de déployer le backend, appliquer `backend/migrations/20261002_pending_requests.sql` à la base PostgreSQL `membres` (par exemple avec `docker compose exec -T db psql -U postgres -d membres < backend/migrations/20261002_pending_requests.sql`). La migration est idempotente. Aucun champ des tables existantes n'est modifié.

Pour accepter les inscriptions non-UMONS sur une base existante, appliquer ensuite `backend/migrations/20261002_non_umons_registration.sql` avant de déployer le nouveau backend. Cette migration conserve les demandes UMONS en attente et garantit qu'une demande utilise soit un matricule, soit un email.

## Contraintes techniques

- Réutiliser le système existant de hashage des mots de passe.
- Garantir l'unicité du matricule ou de l'email au niveau de la base de données.
- Le matricule est stocké dans `member_id` et l'adresse non-UMONS dans `email` ; chacun peut servir à la connexion après validation admin.
- Valider et normaliser les nom, prénom et l'identifiant choisi côté backend.
- Vérifier la confirmation du mot de passe.
- Appliquer des limites raisonnables à la taille des champs.
- Nginx limite `/api/auth/register` à 5 requêtes par minute et par adresse IP (rafale de 5).
- Ne pas attribuer de privilèges de membre avant validation du compte : une demande n'est pas un compte et ne peut pas se connecter.
- Conserver la compatibilité avec les comptes existants.

## Interface d'administration

L'interface `/admin/users` affiche les demandes temporaires dans une file dédiée, séparée des comptes existants.

Un administrateur pourra ensuite :

- vérifier les informations de l'utilisateur ;
- valider son compte, ce qui crée l'utilisateur membre ;
- lui attribuer une carte Fédé ;
- utiliser l'attribution automatique du prochain numéro disponible.

## Évolutions possibles

À terme :

- modification contrôlée des informations personnelles ;
- validation groupée des inscriptions.
