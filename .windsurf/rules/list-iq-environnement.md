---
trigger: always_on
---

L'application List-IQ est une application Web de centralisation de listes

## Environnement:
  - conteneur Docker
  - en 3 microservices Nginx, web et basede données MySQL
  - Language Python avec Flask

## Fonctionnalités principales

### Authentification

L'application prend en charge deux méthodes d'authentification :

1. **Authentification locale** : Utilisateurs stockés dans la base de données de l'application
2. **Authentification LDAP/Active Directory** : Intégration avec un annuaire d'entreprise

#### Configuration LDAP

L'application permet une configuration complète de la connexion LDAP, incluant :

- Connexion sécurisée via LDAPS (SSL) ou StartTLS
- Vérification des certificats SSL/TLS avec support des certificats CA personnalisés
- Mappage des groupes LDAP aux rôles de l'application

Pour plus de détails, consultez la [documentation d'authentification LDAP](docs/ldap_authentication.md).

### Gestion des listes
- Création, édition et suppression de listes
- Import de données depuis diverses sources (CSV, JSON, API)
- Filtrage des données par colonnes
- Restriction d'accès par adresse IP
- Contrôle de visibilité des listes via le statut de publication
  - Les administrateurs peuvent voir toutes les listes
  - Les utilisateurs standards ne peuvent voir que les listes publiées

### Automatisation
- Mise à jour automatique des listes via planification cron
- Exécution de scripts Python personnalisés (via les champs `code` ou `script_content`)
- Exécution de commandes curl pour récupérer des données d'API
- Récupération directe de données depuis des URLs (JSON ou CSV)
- Limite configurable du nombre de résultats importés par liste
- Formatage automatique des données selon les types de colonnes définis
- Gestion sécurisée des certificats SSL pour les requêtes externes

### Configuration JSON avancée
- Extraction de données spécifiques depuis des réponses JSON complexes
- Support de la pagination pour les API
- Sélection des colonnes à importer

### Fichiers publics
- Génération de fichiers TXT, CSV et JSON accessibles sans authentification
- Accès sécurisé via un token unique généré pour chaque liste
- Restriction d'accès par adresse IP configurable
- Mise à jour automatique des fichiers dans tous les cas suivants :
  - Lors des mises à jour programmées des listes
  - Lors de l'ajout manuel de données via l'interface ou l'API
  - Lors de la modification de données via l'interface ou l'API
  - Lors de la suppression (individuelle ou en masse) de données
  - Lors de l'importation de données depuis un fichier
- URLs stables pour l'intégration avec des systèmes externes
- Formats standardisés pour faciliter l'importation des données

### API
- API REST pour accéder aux données des listes
- Ajout, modification et suppression de données via API (réservé aux administrateurs)
- Authentification par tokens API sécurisés
- Interface de gestion des tokens API pour les utilisateurs
  - Création de tokens avec noms personnalisés
  - Possibilité de définir une date d'expiration
  - Affichage sécurisé des tokens générés
  - Exemples d'utilisation avec cURL et Python

#### Authentification API
L'API utilise une authentification par token. Pour accéder aux endpoints protégés, vous devez inclure le token dans l'en-tête HTTP `Authorization` sous forme de Bearer token :

```
Authorization: Bearer votre_token_api
```

#### Génération de tokens API
Les tokens API peuvent être générés depuis l'interface utilisateur dans la section "Profil" > "Tokens API". Chaque token généré est associé à un utilisateur spécifique et hérite de ses droits d'accès.

#### Restrictions d'accès API
L'API implémente un système de contrôle d'accès basé sur les rôles :

- **Utilisateurs standards** : Peuvent uniquement lire les données des listes publiées
- **Administrateurs** : Peuvent lire, ajouter, modifier et supprimer les données des listes

Toutes les actions d'administration des listes (création, modification de structure, gestion des colonnes) ne sont disponibles que via l'interface web et non via l'API.


## Développement
L'application suit une méthodologie TDD (Test Driven Development). Pour chaque nouvelle fonctionnalité :

1. Écrire les tests
2. Vérifier qu'ils échouent
3. Implémenter la fonctionnalité
4. Vérifier que les tests passent
5. Refactoriser si nécessaire


