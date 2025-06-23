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

1.  Unzip the List-IQ archive in the directory of your choice
2.  Configure the environment variables in the `.env` file (see the `.env.example` file)
3.  Start the application with the command:

    ```bash
    docker-compose -f config/docker-compose.yml up -d
    ```

4.  Access the application via your browser at: http://localhost:80

## Package Structure

-   `app/`: Application source code
-   `config/`: Configuration files (docker-compose.yml, SQL scripts)
-   `docs/`: Documentation
-   `scripts/`: Utility scripts

## Configuration

Create a `.env` file at the root of the project with the following variables:

Database Configuration

DB_HOST=db
DB_NAME=listiq
DB_USER=listiq_user
DB_PASSWORD=your_secure_password

Application Configuration

SECRET_KEY=your_secret_key
DEFAULT_LANGUAGE=en # fr or en

Port Configuration

NGINX_PORT=80
NGINX_SSL_PORT=443

Generated code
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
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
IGNORE_WHEN_COPYING_END

To back up the database:

Generated bash
docker exec listiq-db-1 mysqldump -u root -proot listiq > backup.sql
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Bash
IGNORE_WHEN_COPYING_END
Generated code
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
IGNORE_WHEN_COPYING_END