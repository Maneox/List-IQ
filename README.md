# List-IQ

## Overview

List-IQ is a list management web application that allows you to create, manage, and share data lists through an intuitive web interface and a REST API.

## Main Features

-   Creation and management of data lists
-   Multilingual interface (French/English)
-   REST API for programmatic data access
-   User authentication and management
-   Integrated documentation for the API
-   Support for automatic updates via URL or API

## Prerequisites

-   Docker and Docker Compose
-   Network access for containers

## Installation

### Méthode 1 : Installation automatisée avec le script install.sh

Le projet inclut un script d'installation automatisée `install.sh` qui facilite la configuration et le déploiement de l'application sur un environnement Linux.

```bash
# Rendre le script exécutable
chmod +x install.sh

# Lancer le script en mode interactif
./install.sh
```

#### Options disponibles

Le script peut être utilisé de deux façons :

1. **Mode interactif** (sans paramètres) : Affiche un menu avec les options suivantes :
   - Configurer l'installation
   - Démarrer les conteneurs
   - Arrêter les conteneurs
   - Réinitialiser les variables d'installation
   - Quitter

2. **Mode ligne de commande** avec les paramètres suivants :
   ```bash
   ./install.sh [OPTION]
   ```
   Options disponibles :
   - `start` : Démarrer les conteneurs
   - `stop` : Arrêter les conteneurs
   - `help`, `-h`, `--help` : Afficher l'aide

#### Fonctionnalités du script

Le script `install.sh` permet de :

- Configurer les variables d'environnement dans le fichier `.env`
- Gérer la configuration de la base de données
- Configurer les paramètres de l'administrateur
- Gérer les paramètres du serveur
- Configurer un proxy si nécessaire
- Mettre à jour les fichiers de configuration (Dockerfile, docker-compose.yml, nginx.conf)
- Générer automatiquement le fichier d'initialisation de la base de données
- Démarrer et arrêter les conteneurs Docker

### Méthode 2 : Installation manuelle

1.  Décompressez l'archive List-IQ dans le répertoire de votre choix
2.  Configurez les variables d'environnement dans le fichier `.env` (voir le fichier `.env.example`)
3.  Démarrez l'application avec la commande :

    ```bash
    docker-compose -f config/docker-compose.yml up -d
    ```

4.  Accédez à l'application via votre navigateur à l'adresse : http://localhost:80

## Package Structure

-   `app/`: Application source code
-   `docs/`: Documentation
-   `services/`: Services de déploiement

## Configuration

Create a `.env` file at the root app/ of the project with the following variables:

```
# Database Configuration
DB_HOST=db
DB_NAME=listiq
DB_USER=listiq_user
DB_PASSWORD=your_secure_password

# Application Configuration
SECRET_KEY=your_secret_key
DEFAULT_LANGUAGE=en # fr or en

# Port Configuration
NGINX_PORT=80
NGINX_SSL_PORT=443
```
## Usage

Once the application is started, you can:

1.  Log in with the default user (admin/admin)
2.  Create new users
3.  Create and manage lists
4.  Access the API via the integrated documentation

## Maintenance

To update the application:

```bash
docker-compose -f config/docker-compose.yml down
docker-compose -f config/docker-compose.yml up -d --build
```

Pour sauvegarder la base de données :

```bash
docker exec listiq-db-1 mysqldump -u root -proot listiq > backup.sql
```

## Déploiement comme service système

Le répertoire `services` contient deux fichiers de configuration pour déployer l'application List-IQ en tant que service système sur un environnement Linux :

### 1. `listiq.service` (systemd)

Ce fichier est une unité systemd qui permet de gérer l'application List-IQ comme un service système Linux.

**Installation et utilisation :**
- Copiez ce fichier dans `/etc/systemd/system/` sur votre serveur Linux
- Activez et démarrez le service :
  ```bash
  sudo systemctl daemon-reload
  sudo systemctl enable listiq.service
  sudo systemctl start listiq.service
  ```
- Vérifiez le statut :
  ```bash
  sudo systemctl status listiq.service
  ```

Ce service démarre automatiquement l'application via Docker Compose après le démarrage du système.

### 2. `listiq.conf` (Supervisor)

Ce fichier est une configuration pour Supervisor, un système de contrôle de processus pour Linux.

**Installation et utilisation :**
- Installez Supervisor puis copiez ce fichier dans `/etc/supervisor/conf.d/`
- Activez la configuration :
  ```bash
  sudo supervisorctl reread
  sudo supervisorctl update
  ```
- Gérez les services :
  ```bash
  sudo supervisorctl status listiq
  sudo supervisorctl start listiq
  sudo supervisorctl stop listiq
  ```

**Remarque :** Les deux configurations supposent que l'application est installée dans `/opt/list-iq` sur le serveur Linux.
