
# List-IQ

## Overview

List-IQ is a list management web application that allows you to create, manage, and share data lists through an intuitive web interface and a REST API.

## Main Features

- Creation and management of data lists  
- Multilingual interface (French/English)  
- REST API for programmatic data access  
- User authentication and management  
- Integrated API documentation  
- Support for automatic updates via URL or API  

## Prerequisites

- Docker and Docker Compose  

Create List-IQ local user & directory
We recommend configuring your Linux server with a dedicated List-IQ service account, from which to install and run List-IQ. Doing so will isolate your List-IQ instance from other applications running on your server.

These steps are List-IQ-recommended best practices, but are not required. For more information, see Docker's Post-installation steps for Linux documentation.

Create a List-IQ user:

```Bash

sudo adduser listiq
```
Set password for listiq user (strong password):

```Bash

sudo passwd listiq
```
Create a docker group (if it doesn’t already exist):

```Bash

sudo groupadd docker
```
Add the listiq user to the docker group:

```Bash

sudo usermod -aG docker listiq
```
Create a List-IQ directory:

```Bash

sudo mkdir /opt/List-IQ
```
Set permissions for the /opt/List-IQ directory:

```Bash

sudo chmod -R 700 /opt/List-IQ
```
Set the List-IQ user as owner of the /opt/List-IQ directory:

```Bash

sudo chown -R listiq:listiq /opt/List-IQ

sudo mkdir /opt/List-IQ
```
Set permissions for the /opt/List-IQ directory:

```Bash

sudo chmod -R 700 /opt/List-IQ
```
Set the List-IQ user as owner of the /opt/List-IQ directory:

```Bash

sudo chown -R listiq:listiq /opt/List-IQ
```

## Installation

### Method 1: Automated Installation with `install.sh` Script

The project includes an automated installation script `install.sh` that simplifies the setup and deployment of the application on a Linux environment.

```bash
# Make the script executable
chmod +x install.sh

# Run the script in interactive mode
./install.sh
```

#### Available Options

The script can be used in two ways:

1. **Interactive Mode** (without parameters): Displays a menu with the following options:
   - Configure installation  
   - Start containers  
   - Stop containers  
   - Reset installation variables  
   - Exit  

2. **Command-line Mode** with the following parameters:
   ```bash
   ./install.sh [OPTION]
   ```
   Available options:
   - `start`: Start the containers  
   - `stop`: Stop the containers  
   - `help`, `-h`, `--help`: Display help  

#### Script Features

The `install.sh` script allows you to:

- Configure environment variables in the `.env` file  
- Manage database configuration  
- Configure administrator settings  
- Manage server parameters  
- Configure a proxy if necessary  
- Update configuration files (Dockerfile, docker-compose.yml, nginx.conf)  
- Automatically generate the database initialization file  
- Start and stop Docker containers  

### Method 2: Manual Installation

1. Extract the List-IQ archive into the directory of your choice  
2. Configure the environment variables in the `.env` file (refer to `.env.example`)  
3. Start the application with the command:

    ```bash
    docker-compose -f config/docker-compose.yml up -d
    ```

4. Access the application in your browser at: http://localhost:80  

## Package Structure

- `app/`: Application source code  
- `docs/`: Documentation  
- `services/`: Deployment services  

## Configuration

Create a `.env` file at the root `app/` directory of the project with the following variables:

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

Once the application is running, you can:

1. Log in with the default user (admin/admin)  
2. Create new users  
3. Create and manage lists  
4. Access the API through the integrated documentation  

## Maintenance

To update the application:

```bash
docker-compose -f config/docker-compose.yml down
docker-compose -f config/docker-compose.yml up -d --build
```

To back up the database:

```bash
docker exec listiq-db-1 mysqldump -u root -proot listiq > backup.sql
```

## Deployment as a System Service

The `services` directory contains two configuration files for deploying List-IQ as a system service on a Linux environment:

### 1. `listiq.service` (systemd)

This file is a systemd unit that allows you to manage List-IQ as a Linux system service.

**Installation and Usage:**  
- Copy this file to `/etc/systemd/system/` on your Linux server  
- Enable and start the service:  
  ```bash
  sudo systemctl daemon-reload
  sudo systemctl enable listiq.service
  sudo systemctl start listiq.service
  ```
- Check the status:  
  ```bash
  sudo systemctl status listiq.service
  ```

This service automatically starts the application via Docker Compose after system boot.

### 2. `listiq.conf` (Supervisor)

This file is a configuration for Supervisor, a process control system for Linux.

**Installation and Usage:**  
- Install Supervisor and copy this file to `/etc/supervisor/conf.d/`  
- Enable the configuration:  
  ```bash
  sudo supervisorctl reread
  sudo supervisorctl update
  ```
- Manage services:  
  ```bash
  sudo supervisorctl status listiq
  sudo supervisorctl start listiq
  sudo supervisorctl stop listiq
  ```

**Note:** Both configurations assume the application is installed in `/opt/list-iq` on the Linux server.
