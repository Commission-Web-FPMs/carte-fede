# Comptes DEV automatiques et cartes administrées

Cette fonctionnalité exige `APP_ENV=development`, la base et le propriétaire
`carte_fede_dev`, OIDC DEV et `DEV_EMAIL_REGISTRATION_ENABLED=1`. La production
Flask conserve son comportement. Aucun DDL supplémentaire n’est nécessaire.

Le premier formulaire Authentik demande nom, prénom et matricule UMons à six
chiffres ou e-mail. Le username technique est généré côté serveur. Un matricule
et son adresse `NNNNNN@umons.ac.be` utilisent la même clé de collision, sans
constituer une preuve d’identité ni permettre une adoption de profil existant.

La nouvelle identité est inactive, sans mot de passe utilisable, dans le seul
périmètre détenu par le flow DEV. Après confirmation du lien natif HTTPS
(30 minutes), le formulaire natif recueille le mot de passe. Le stage de
confirmation natif révoque le token ; le garde du mot de passe enregistre aussi
son empreinte consommée sous verrou de ligne, atomiquement avec le mot de passe.
Deux onglets déjà restaurés ne peuvent donc écrire deux mots de passe. Aucun
mot de passe ni token d’e-mail n’est transmis à Flask.

Les inscriptions et renvois sont limités ; les contacts utilisés, hors périmètre
ou indisponibles reçoivent une réponse générique. Les réservations sont
sérialisées par contact canonique dans Authentik et PostgreSQL. Les quatre
inscriptions historiques restent exclues de l’activation automatique : la
présence d’une demande ancienne ne vaut jamais preuve native.

Le journal PostgreSQL passe par `email_pending`, puis `provisioning`. Un profil
ATTENTE avec UUID durable précède l’activation distante. L’identité détenue DEV
ne reçoit `membres` et son activation qu’après preuve native persistée. Le
profil devient MEMBER après confirmation. Une reprise garde le même UUID. Si
l’activation distante a réussi avant une panne locale, la connexion native de
cette identité permet de reprendre sa finalisation vérifiée.

Une identité active existante s’authentifie par OIDC. Si elle n’a pas de mapping,
le flow authentifié recueille ses informations métier puis crée un profil
MEMBER local ; une nouvelle connexion OIDC confirme l’association issuer/sub.
Ses credentials, groupes et permissions Authentik ne sont pas modifiés. Les
mappings historiques conservent leur UUID et leur rôle PostgreSQL.

**Aucune carte et aucune demande de carte ne sont créées par ces opérations.**
Le membre demande une carte explicitement. Seul ADMIN peut approuver/refuser et
doit confirmer le paiement ou vérifier BAC1. ADMIN, VERIFIER et MEMBER restent
des rôles PostgreSQL, contrôlés à chaque requête ; aucun rôle n’est synchronisé
vers Authentik. Le groupe partagé `membres` ouvre aussi l’application SSO
`carte-fede-main`, conformément à la décision opérateur du 13 octobre 2026.

DEV utilise le SMTP commun existant de Carte Fédé, STARTTLS, dans un EmailStage
dédié. Le SMTP global Authentik et les autres applications sont inchangés.
Les tests automatisés de nouveau compte utilisent le clone et Mailpit isolé ;
les contrôles du SMTP réel s’arrêtent à AUTH/NOOP, sans transmission de message.
Les credentials réels restent dans les Secrets/SealedSecrets ; jamais dans les
scripts, logs affichés, fixtures ou sources en clair.

Déployer d’abord le backend avec le flag désactivé, puis les flows et le Secret
SMTP DEV, enfin activer le flag dans le chart develop. Avant le dernier point,
le nouveau flow reste fermé par le hook. En cas de panne, désactiver ce flag et
fermer l’inscription DEV ; conserver les identités/profils/journaux pour reprise.
Ne pas restaurer l’ancienne approbation sur des dossiers `email_pending` ou
`provisioning`, ni restaurer une sauvegarde sur une base ayant reçu des écritures
sans revue séparée. Aucun rollback automatique de production.
