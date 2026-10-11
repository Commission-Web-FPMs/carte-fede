# Carte Fédé DEV — develop uniquement

Environnement `https://carte-dev.fede.fpms.ac.be`, namespace `carte-fede-dev`, rôle et base `carte_fede_dev` sur PG18 ICU déterministe en-US. Production suit `main`, ses images et son namespace ; ne pas fusionner automatiquement les valeurs/chart DEV ni les réglages OIDC vers main.

## Publication

Le workflow de develop exécute les tests confidentialité/OIDC et la recette PostgreSQL18 jetable, compile le frontend, publie uniquement `ghcr.io/commission-web-fpms/carte-fede-dev:<SHA40>` et `carte-fede-dev-frontend:<SHA40>`, puis met à jour exclusivement `develop` de carte-fede-deployment. Aucun tag latest, aucun push main. GitOps suit la branche chart develop ; synchronisation automatique normale, aucune commande Argo forcée.

`AUTH_MODE=oidc` exige `APP_ENV=development`, base/rôle carte_fede_dev et issuer/client/origin DEV exacts. La branche stable main reste Flask. Les secrets DEV sont indépendants, SealedSecrets strictement liés au namespace/nom, avec récupération locale AES256 hors Git. Les comptes synthétiques et mots de passe ne doivent pas être affichés dans un terminal ou déposés dans Git ; les credentials sont disponibles dans l'archive chiffrée de récupération opérateur.

## Identités et sessions

Groupe Authentik `carte-fede-dev-testers`, sans rôle Authentik/superuser/parent. Quatre comptes synthétiques : admin/verifier/member actifs, attente désactivé. Les UUID Authentik et métier synthétiques sont distincts ; sub_mode user_uuid. Le secret contient un mapping autoritaire fixe sub→UUID, associé à l'issuer DEV exact. Aucune adoption par email/identifiant, aucune création utilisateur au premier login ; un claim changé reste refusé même signé. Les rôles métier viennent uniquement de PostgreSQL.

Authorization Code, PKCE S256, state/nonce uniques à usage unique, callback HTTPS strict ; signatures RS256 et issuer/audience/exp/iat/azp vérifiés. Cookies __Host-carte-fede-dev Secure/HttpOnly/SameSite=Lax ; tokens uniquement dans des sessions serveur éphémères privées, aucun localStorage/cookie/JWT d'accès lisible. Une réinstallation invalide ces sessions. Userinfo à chaque requête vérifie l'activation et le groupe DEV ; défaillance Authentik ferme l'accès. Session cinq minutes au maximum, pas de refresh_token. Logout local révoque le token ; un SSO Authentik encore actif permet une nouvelle connexion explicite.

Toutes les API métier et /verify requièrent une identité DEV. Origin exact exigé pour les écritures. Authentification Flask locale, inscriptions ouvertes, resets/passwords locaux bloqués en mode OIDC DEV. Frontend public et page de login publics ; aucune donnée métier publique. Rate limit dédié sur login/callback et protections NPM-only.

## Données synthétiques / sécurité externe

Initialisation PreSync `python scripts/init_dev_data.py` idempotente, guards vérifiés avant tout SQL et current_database/current_user vérifiés avant création du schéma. Neuf tables métier, quatre utilisateurs, trois cartes, une inscription pending ; aucun import/dump de production. SMTP délibérément ignoré sans logs de contenu ; aucun credential SMTP. Toutes les API paiement et configuration bancaire interdites, IBAN/BIC vides, montant nul. NetworkPolicy ingress seulement Traefik et egress uniquement DNS, PostgreSQL et HTTPS NPM/Authentik ; aucune sortie SMTP/banque.

Une remise à zéro efface uniquement DEV et requiert un choix explicite :

```bash
kubectl --context comweb-k8s-dev -n carte-fede-dev exec deployment/carte-fede-dev -- python scripts/init_dev_data.py --reset-synthetic-dev
```

Ne pas exécuter contre un autre namespace ni effectuer de rapprochement automatique d'inscriptions validées avec un compte Authentik existant. Pour tester une nouvelle association, ajouter explicitement le compte synthétique et son binding vérifié ; l'état ATTENTE et la désactivation doivent rester refusés.

## Validation et rollback

Tests unitaires JWT/claims/signature/state/PKCE/DB guard, tests de confidentialité, requêtes réelles login/logout/401/403/rôles/attente/session désactivée, absence d'emails/paiements. Surveiller CNPG3/3, trois nœuds Ready, Argo Healthy, aucune modification des Deployments/credentials/providers/comptes de production ; les écritures légitimes de production peuvent continuer.

Rollback de code : mettre une version SHA déjà validée dans develop du chart puis laisser Argo réconcilier. Une nouvelle publication applicative produit une nouvelle SHA et ne doit pas réutiliser un tag. En urgence fermer uniquement l'hôte NPM DEV par le guard opérateur ; garder toutes les ressources historiques et bases. Annulation des changements Traefik uniquement après fermeture DEV, revert de l'ajout du namespace (maxUnavailable0), sondes production vérifiées. Ne jamais restaurer globalement PostgreSQL/Authentik/NPM pour annuler DEV ; ne jamais modifier un hôte NPM de production. Les Database/DatabaseRole sont retain et protégés Prune=false/Delete=false. Aucun finalizer de suppression cascaded d'Application ajouté. Aucune bascule OIDC de production autorisée par DEV.
