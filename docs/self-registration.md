# Self-registration

## Objectif

Permettre aux nouveaux utilisateurs de créer eux-mêmes leur compte sur le site de la carte Fédé, sans nécessiter la création manuelle du compte par un administrateur.

## Flux envisagé

1. L'utilisateur accède à une page publique `/register/`.
2. Il renseigne :
   - prénom ;
   - nom ;
   - matricule ;
   - mot de passe ;
   - confirmation du mot de passe.
3. Le backend valide et normalise les données.
4. Le compte est créé avec le rôle `en attente`.
5. Aucune carte Fédé n'est attribuée automatiquement lors de l'inscription.
6. Un administrateur vérifie et valide ensuite le compte.
7. Une carte peut être attribuée via le système d'administration existant.

## Contraintes techniques

- Réutiliser le système existant de hashage des mots de passe.
- Garantir l'unicité du matricule au niveau de la base de données.
- Déterminer si le champ `identifiant` existant doit représenter directement le matricule afin d'éviter de dupliquer l'information.
- Valider et normaliser les nom, prénom et matricule côté backend.
- Vérifier la confirmation du mot de passe.
- Appliquer des limites raisonnables à la taille des champs.
- Prévoir une protection contre les créations de comptes abusives et les tentatives répétées.
- Ne pas attribuer de privilèges de membre avant validation du compte.
- Conserver la compatibilité avec les comptes existants.

## Interface d'administration

L'interface `/admin/users` devra permettre d'identifier facilement les comptes ayant le rôle `en attente`.

Un administrateur pourra ensuite :

- vérifier les informations de l'utilisateur ;
- valider son compte en modifiant son rôle ;
- lui attribuer une carte Fédé ;
- utiliser l'attribution automatique du prochain numéro disponible.

## Évolutions possibles

À terme :

- modification du mot de passe ;
- récupération de mot de passe ;
- modification contrôlée des informations personnelles ;
- vue dédiée aux inscriptions en attente ;
- validation groupée des inscriptions.
