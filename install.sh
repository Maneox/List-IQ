#!/bin/bash

# Installation script for List-IQ
# This script configures the environment and prepares the database
cd app/
# Check if the script is run with root privileges
# if [ "$(id -u)" != "0" ]; then
#    echo "This script must be run as root" 
#    exit 1
# fi

# Define colors for messages
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to display messages
print_message() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_section() {
    echo -e "\n${BLUE}[SECTION]${NC} $1"
    echo -e "${BLUE}$(printf '=%.0s' {1..50})${NC}"
}

# Check if the .env file exists
if [ ! -f ".env" ]; then
    print_error "The .env file does not exist. Please create it before continuing."
    exit 1
fi

# Load environment variables
print_message "Loading environment variables..."
set -a
source .env
set +a

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install it before continuing."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    print_error "Docker Compose is not installed. Please install it before continuing."
    exit 1
fi

# Function to update the Dockerfile
update_dockerfile() {
    use_proxy=$1
    proxy_url=$2
    proxy_exclusion=$3
    
    print_message "Updating Dockerfile..."
    
    # Backing up the original Dockerfile
    cp ../Dockerfile ../Dockerfile.bak
    
    if [[ $use_proxy =~ ^[Yy][Ee][Ss]$ ]]; then
        # Check if proxy variables already exist in the Dockerfile
        if grep -q "ENV http_proxy" ../Dockerfile; then
            # Update existing proxy variables
            sed -i "s|ENV http_proxy.*|ENV http_proxy $proxy_url|g" ../Dockerfile
            sed -i "s|ENV https_proxy.*|ENV https_proxy $proxy_url|g" ../Dockerfile
            sed -i "s|ENV no_proxy.*|ENV no_proxy $proxy_exclusion|g" ../Dockerfile
        else
            # Add proxy variables after the FROM line
            sed -i "/^FROM/a ENV http_proxy $proxy_url\nENV https_proxy $proxy_url\nENV no_proxy $proxy_exclusion" ../Dockerfile
        fi
        
        # Check if apt configuration for the proxy already exists
        if grep -q "Acquire::http::Proxy" ../Dockerfile; then
            print_message "apt configuration for proxy already present in Dockerfile"
        else
            # Add apt configuration for the proxy after the environment variables
            apt_config="# Configure apt to use the proxy\nRUN if [ -n \"\$HTTP_PROXY\" ]; then \\\\\n        echo \"Acquire::http::Proxy \\\"\$HTTP_PROXY\\\";\" > /etc/apt/apt.conf.d/proxy.conf && \\\\\n        echo \"Acquire::https::Proxy \\\"\$HTTPS_PROXY\\\";\" >> /etc/apt/apt.conf.d/proxy.conf; \\\\\n    fi"
            
            sed -i "/ENV no_proxy/a $apt_config" ../Dockerfile
        fi
        
        print_message "Proxy configuration added to Dockerfile"
    else
        # Remove proxy variables and apt configuration for the proxy
        sed -i "/ENV http_proxy/d" ../Dockerfile
        sed -i "/ENV https_proxy/d" ../Dockerfile
        sed -i "/ENV no_proxy/d" ../Dockerfile
        sed -i "/Configure apt to use the proxy/d" ../Dockerfile
        sed -i "/RUN if \[ -n \"\$HTTP_PROXY\" \]; then/,+3d" ../Dockerfile
        
        print_message "Proxy configuration removed from Dockerfile"
    fi
}

# Function to update the docker-compose.yml
update_docker_compose() {
    server_name=$1
    
    print_message "Updating docker-compose.yml..."
    
    # Backing up the original docker-compose.yml
    cp ../docker-compose.yml ../docker-compose.yml.bak  
    # Update SSL_CERT_URL in docker-compose.yml
    if grep -q "SSL_CERT_URL" ../docker-compose.yml; then
        sed -i "s|SSL_CERT_URL=.*|SSL_CERT_URL=https://$server_name|g" ../docker-compose.yml
        print_message "SSL_CERT_URL updated in docker-compose.yml"
    else
        print_warning "SSL_CERT_URL not found in docker-compose.yml"
    fi
}

# Function to update the nginx.conf
update_nginx_conf() {
    server_name=$1
    
    print_message "Updating nginx.conf..."
    
    # Check if the nginx directory exists
    if [ ! -d "nginx" ]; then
        print_error "The nginx directory does not exist"
        return 1
    fi
    
    # Check if the nginx.conf file exists
    if [ ! -f "nginx/nginx.conf" ]; then
        print_error "The nginx.conf file does not exist"
        return 1
    fi
    
    # Backing up the original nginx.conf
    cp nginx/nginx.conf nginx/nginx.conf.bak
    
    # Update server_name in nginx.conf
    # Search for lines containing server_name and modify them
    sed -i "s/server_name localhost .*/server_name localhost $server_name;/g" nginx/nginx.conf
    
    print_message "server_name updated in nginx.conf"
}

# Function to configure the installation
configure_installation() {
    print_section "Installation Configuration"
    
    # Database Configuration
    print_section "Database Configuration"
    read -p "Database username [${DB_USER}]: " db_user
    db_user=${db_user:-${DB_USER}}
    
    read -p "Database password [${DB_PASSWORD}]: " db_password
    db_password=${db_password:-${DB_PASSWORD}}
    
    read -p "Database name [${DB_NAME}]: " db_name
    db_name=${db_name:-${DB_NAME}}
    
    # Update database variables in the .env file
    sed -i "s/DB_USER=.*/DB_USER=$db_user/g" .env
    sed -i "s/DB_PASSWORD=.*/DB_PASSWORD=$db_password/g" .env
    sed -i "s/DB_NAME=.*/DB_NAME=$db_name/g" .env
    print_message "Database configuration updated"
    
    # Administrator Configuration
    print_section "Administrator Configuration"
    read -p "Administrator username [${ADMIN_USERNAME}]: " admin_username
    admin_username=${admin_username:-${ADMIN_USERNAME}}
    
    read -p "Administrator email [${ADMIN_EMAIL}]: " admin_email
    admin_email=${admin_email:-${ADMIN_EMAIL}}
    
    read -p "Administrator password [${ADMIN_PASSWORD}]: " admin_password
    admin_password=${admin_password:-${ADMIN_PASSWORD}}
    
    # Update administrator variables in the .env file
    sed -i "s/ADMIN_USERNAME=.*/ADMIN_USERNAME=$admin_username/g" .env
    sed -i "s/ADMIN_EMAIL=.*/ADMIN_EMAIL=$admin_email/g" .env
    sed -i "s/ADMIN_PASSWORD=.*/ADMIN_PASSWORD=$admin_password/g" .env
    print_message "Administrator configuration updated"
    
    # Server Configuration
    print_section "Server Configuration"
    read -p "Server name [${SERVER_NAME}]: " server_name
    server_name=${server_name:-${SERVER_NAME}}
    
    read -p "Flask environment (development/production) [${FLASK_ENV}]: " flask_env
    flask_env=${flask_env:-${FLASK_ENV}}
    
    # Update server variables in the .env file
    sed -i "s/SERVER_NAME=.*/SERVER_NAME=$server_name/g" .env
    sed -i "s/FLASK_ENV=.*/FLASK_ENV=$flask_env/g" .env
    print_message "Server configuration updated"
    
    # Proxy Configuration
    print_section "Proxy Configuration"
    read -p "Configure a proxy? (yes/no) [no]: " configure_proxy
    configure_proxy=${configure_proxy:-no}
    
    if [[ $configure_proxy =~ ^[Yy][Ee][Ss]$ ]]; then
        read -p "Proxy server [proxy.domain.local]: " proxy_server
        proxy_server=${proxy_server:-proxy.domain.local}
        
        read -p "Proxy port [8080]: " proxy_port
        proxy_port=${proxy_port:-8080}
        
        read -p "Proxy user []: " proxy_user
        
        read -p "Proxy password []: " proxy_password
        
        read -p "Proxy exclusions [localhost,127.0.0.1,db,web,nginx,.local,$server_name]: " proxy_exclusion
        proxy_exclusion=${proxy_exclusion:-localhost,127.0.0.1,db,web,nginx,.local,$server_name}
        
        read -p "Verify SSL certificates? (true/false) [false]: " verify_ssl
        verify_ssl=${verify_ssl:-false}
        
        # Build the proxy URL
        if [ -n "$proxy_user" ] && [ -n "$proxy_password" ]; then
            proxy_url="http://$proxy_user:$proxy_password@$proxy_server:$proxy_port"
        else
            proxy_url="http://$proxy_server:$proxy_port"
        fi
        
        # Update proxy variables in the .env file
        sed -i "s|HTTP_PROXY=.*|HTTP_PROXY=$proxy_url|g" .env
        sed -i "s|HTTPS_PROXY=.*|HTTPS_PROXY=$proxy_url|g" .env
        sed -i "s|NO_PROXY=.*|NO_PROXY=$proxy_exclusion|g" .env
        sed -i "s|http_proxy=.*|http_proxy=\${HTTP_PROXY}|g" .env
        sed -i "s|https_proxy=.*|https_proxy=\${HTTPS_PROXY}|g" .env
        sed -i "s|no_proxy=.*|no_proxy=\${NO_PROXY}|g" .env
        sed -i "s/VERIFY_SSL=.*/VERIFY_SSL=$verify_ssl/g" .env
        print_message "Proxy configuration updated"
    else
        # Disable proxy
        sed -i "s|HTTP_PROXY=.*|HTTP_PROXY=|g" .env
        sed -i "s|HTTPS_PROXY=.*|HTTPS_PROXY=|g" .env
        sed -i "s|NO_PROXY=.*|NO_PROXY=localhost,127.0.0.1,db,web,nginx,.local,$server_name|g" .env
        sed -i "s|http_proxy=.*|http_proxy=|g" .env
        sed -i "s|https_proxy=.*|https_proxy=|g" .env
        sed -i "s|no_proxy=.*|no_proxy=localhost,127.0.0.1,db,web,nginx,.local,$server_name|g" .env
        print_message "Proxy disabled"
    fi
    
    # Log Configuration
    print_section "Log Configuration"
    read -p "Log level (debug/info/warning/error) [${LOG_LEVEL}]: " log_level
    log_level=${log_level:-${LOG_LEVEL}}
    
    # Update the log level variable in the .env file
    sed -i "s/LOG_LEVEL=.*/LOG_LEVEL=$log_level/g" .env
    print_message "Log configuration updated"
    
    # Default Language Configuration
    print_section "Language Configuration"
    read -p "Default language (fr/en) [${DEFAULT_LANGUAGE:-fr}]: " default_language
    default_language=${default_language:-${DEFAULT_LANGUAGE:-fr}}
    
    # Check if the language is valid
    if [ "$default_language" != "fr" ] && [ "$default_language" != "en" ]; then
        print_warning "Unsupported language. Using French by default."
        default_language="fr"
    fi
    
    # Update or add the language variable in the .env file
    if grep -q "DEFAULT_LANGUAGE" .env; then
        sed -i "s/DEFAULT_LANGUAGE=.*/DEFAULT_LANGUAGE=$default_language/g" .env
    else
        echo "" >> .env
        echo "# Language Configuration" >> .env
        echo "DEFAULT_LANGUAGE=$default_language" >> .env
    fi
    print_message "Language configuration updated ($default_language)"
    
    # Dockerfile Configuration
    print_section "Dockerfile Configuration"
    read -p "Use proxy for container build? (yes/no) [no]: " use_proxy_for_build
    use_proxy_for_build=${use_proxy_for_build:-no}
    
    # Update the Dockerfile for proxy configuration
    update_dockerfile "$use_proxy_for_build" "$proxy_url" "$proxy_exclusion"
    
    # docker-compose.yml Configuration
    print_section "docker-compose.yml Configuration"
    update_docker_compose "$server_name"
    
    # nginx.conf Configuration
    print_section "nginx.conf Configuration"
    update_nginx_conf "$server_name"
    
    # Ask the user if they want to perform a new installation
    print_section "Installation Options"
    read -p "Perform a new installation? (yes/no) [no]: " new_install
    if [[ $new_install =~ ^[Yy][Ee][Ss]$ ]]; then
        sed -i 's/NEW_INSTALL=false/NEW_INSTALL=true/g' .env
        print_message "NEW_INSTALL variable set to true"
    else
        sed -i 's/NEW_INSTALL=true/NEW_INSTALL=false/g' .env
    fi
    
    # Ask the user if they want to reset the admin account
    read -p "Reset the administrator account? (yes/no) [no]: " reset_admin
    if [[ $reset_admin =~ ^[Yy][Ee][Ss]$ ]]; then
        sed -i 's/RESET_ADMIN=false/RESET_ADMIN=true/g' .env
        print_message "RESET_ADMIN variable set to true"
    else
        sed -i 's/RESET_ADMIN=true/RESET_ADMIN=false/g' .env
    fi
    
    # Ask the user if they want to update the application
    read -p "Update the application? (yes/no) [no]: " update_app
    if [[ $update_app =~ ^[Yy][Ee][Ss]$ ]]; then
        sed -i 's/UPDATE=false/UPDATE=true/g' .env
        print_message "UPDATE variable set to true"
    else
        sed -i 's/UPDATE=true/UPDATE=false/g' .env
    fi
    
    print_message "Configuration completed successfully"
}

# Function to start the containers
start_containers() {
    print_section "Starting Containers"
    
    # Generate the init.sql file before starting the containers if necessary
    if grep -q "NEW_INSTALL=true" .env; then
        print_message "New installation detected, generating init.sql file..."
        generate_init_sql
    else
        print_message "No new installation, clearing the content of init.sql file..."
        clear_init_sql
    fi
    
    # Stop existing containers
    docker-compose down
    
    # Build and start containers
    docker-compose up -d --build
    
    # Check the status of the db container after startup
    sleep 5
    db_status=$(docker-compose ps -q db | xargs docker inspect -f '{{.State.Status}}' 2>/dev/null)
    if [ "$db_status" = "exited" ]; then
        print_warning "The db container has stopped. Waiting 10 seconds before restarting..."
        sleep 10
        docker-compose start db
        print_message "Restarting db container. Waiting for availability..."
    fi
    
    # Wait for the db container to be healthy or running
    for i in {1..12}; do
        db_health=$(docker inspect --format='{{.State.Health.Status}}' $(docker-compose ps -q db) 2>/dev/null)
        db_status=$(docker-compose ps -q db | xargs docker inspect -f '{{.State.Status}}' 2>/dev/null)
        if [[ "$db_health" == "healthy" || "$db_status" == "running" ]]; then
            print_message "The db container is ready ($db_health/$db_status)"
            break
        fi
        print_message "Waiting for db container to be available... ($i/12)"
        sleep 5
    done
    
    # Check if the containers are running
    if [ $? -eq 0 ]; then
        print_success "Containers started successfully"
    else
        print_error "Error starting containers"
        exit 1
    fi
}

# Function to stop the containers
stop_containers() {
    print_section "Stopping Containers"
    
    # Check if containers are running
    if [ -z "$(docker-compose ps -q 2>/dev/null)" ]; then
        print_warning "No running containers"
        return 0
    fi
    
    # Stop running containers
    print_message "Stopping running containers..."
    docker-compose down
    
    # Check if containers are stopped
    if [ -z "$(docker-compose ps -q 2>/dev/null)" ]; then
        print_success "Containers stopped successfully"
    else
        print_error "Error stopping containers"
        exit 1
    fi
}

# Function to clear the init.sql file
clear_init_sql() {
    # Check if init.sql exists and clear it
    if [ -f "../app/init.sql" ]; then
        echo "" > ../app/init.sql
    fi
}

# Function to reset variables after installation
reset_variables() {
    print_message "Resetting installation variables..."
    
    # Reset variables in the .env file
    sed -i 's/NEW_INSTALL=true/NEW_INSTALL=false/g' .env
    sed -i 's/RESET_ADMIN=true/RESET_ADMIN=false/g' .env
    sed -i 's/UPDATE=true/UPDATE=false/g' .env
    clear_init_sql
    print_message "Variables reset successfully"
}

# Function to generate the init.sql file
generate_init_sql() {
    print_section "Generating init.sql file"
    
    # Reload environment variables to get the latest values
    print_message "Reloading environment variables..."
    set -a
    source .env
    set +a
    
    # Check if init.sql is a folder and delete it if so
    if [ -d "../app/init.sql" ]; then
        print_message "Deleting existing init.sql folder..."
        rm -rf ../app/init.sql
    fi
    
    # Check if init.sql is a file and back it up if so
    if [ -f "../app/init.sql" ]; then
        print_message "Backing up existing init.sql file..."
        mv ../app/init.sql ../app/init.sql.bak
    fi
    
    print_message "Creating init.sql file with database information..."
    print_message "Using parameters: DB_NAME=${DB_NAME}, DB_USER=${DB_USER}"
    
    # Back up the old init.sql file if it exists
    if [ -f "../app/init.sql" ]; then
        print_message "Backing up old init.sql file..."
        cp ../app/init.sql ../app/init.sql.bak
    fi
    
    print_message "Creating init.sql file with the integrated database structure..."
    
    # Create the init.sql file directly with all necessary content
    cat > ../app/init.sql << 'EOF'
-- Database initialization script for List-IQ
-- Automatically generated by install.sh on $(date)

-- Create database if it does not exist
CREATE DATABASE IF NOT EXISTS `${DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Create user and grant privileges
CREATE USER IF NOT EXISTS '${DB_USER}'@'%' IDENTIFIED BY '${DB_PASSWORD}';
GRANT ALL PRIVILEGES ON `${DB_NAME}`.* TO '${DB_USER}'@'%';

-- Ensure privileges are applied immediately
FLUSH PRIVILEGES;

-- Use the database
USE `${DB_NAME}`;

-- Database structure
DROP TABLE IF EXISTS `users`;
CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(80) NOT NULL,
  `email` varchar(120) DEFAULT NULL,
  `password_hash` varchar(256) DEFAULT NULL,
  `is_admin` tinyint(1) DEFAULT NULL,
  `is_active` tinyint(1) DEFAULT NULL,
  `auth_type` varchar(20) DEFAULT NULL,
  `last_login` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`),
  UNIQUE KEY `email` (`email`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

DROP TABLE IF EXISTS `api_tokens`;
CREATE TABLE `api_tokens` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `token` varchar(64) NOT NULL,
  `name` varchar(100) NOT NULL,
  `is_active` tinyint(1) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `expires_at` datetime DEFAULT NULL,
  `last_used_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `token` (`token`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `api_tokens_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

DROP TABLE IF EXISTS `ldap_config`;
CREATE TABLE `ldap_config` (
  `id` int NOT NULL AUTO_INCREMENT,
  `enabled` tinyint(1) DEFAULT NULL,
  `host` varchar(255) DEFAULT NULL,
  `port` int DEFAULT NULL,
  `use_ssl` tinyint(1) DEFAULT NULL,
  `use_tls` tinyint(1) DEFAULT NULL,
  `ca_cert` text,
  `verify_cert` tinyint(1) DEFAULT NULL,
  `bind_dn` varchar(255) DEFAULT NULL,
  `bind_password` varchar(255) DEFAULT NULL,
  `base_dn` varchar(255) DEFAULT NULL,
  `user_dn` varchar(255) DEFAULT NULL,
  `group_dn` varchar(255) DEFAULT NULL,
  `user_rdn_attr` varchar(64) DEFAULT NULL,
  `user_login_attr` varchar(64) DEFAULT NULL,
  `user_object_class` varchar(64) DEFAULT NULL,
  `admin_group` varchar(255) DEFAULT NULL,
  `user_group` varchar(255) DEFAULT NULL,
  `group_member_attr` varchar(64) DEFAULT NULL,
  `group_object_class` varchar(64) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

DROP TABLE IF EXISTS `lists`;
CREATE TABLE `lists` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `description` text,
  `user_id` int DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `update_type` varchar(20) NOT NULL,
  `update_schedule` varchar(100) DEFAULT NULL,
  `update_config` text,
  `last_update` datetime DEFAULT NULL,
  `json_config_status` varchar(20) DEFAULT NULL,
  `json_data_path` varchar(255) DEFAULT NULL,
  `json_pagination_enabled` tinyint(1) DEFAULT NULL,
  `json_next_page_path` varchar(255) DEFAULT NULL,
  `json_max_pages` int DEFAULT NULL,
  `json_selected_columns` text,
  `data_source_format` varchar(20) DEFAULT NULL,
  `max_results` int DEFAULT NULL,
  `is_active` tinyint(1) DEFAULT NULL,
  `is_published` tinyint(1) DEFAULT NULL,
  `filter_enabled` tinyint(1) DEFAULT NULL,
  `filter_rules` text,
  `ip_restriction_enabled` tinyint(1) DEFAULT NULL,
  `allowed_ips` text,
  `public_csv_enabled` tinyint(1) DEFAULT NULL,
  `public_json_enabled` tinyint(1) DEFAULT NULL,
  `public_access_token` varchar(64) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `public_access_token` (`public_access_token`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `lists_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

DROP TABLE IF EXISTS `list_columns`;
CREATE TABLE `list_columns` (
  `id` int NOT NULL AUTO_INCREMENT,
  `list_id` int NOT NULL,
  `name` varchar(100) NOT NULL,
  `position` int NOT NULL,
  `column_type` varchar(50) NOT NULL,
  `created_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_name_per_list` (`list_id`,`name`),
  UNIQUE KEY `unique_position_per_list` (`list_id`,`position`),
  CONSTRAINT `list_columns_ibfk_1` FOREIGN KEY (`list_id`) REFERENCES `lists` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=15 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

DROP TABLE IF EXISTS `list_data`;
CREATE TABLE `list_data` (
  `id` int NOT NULL AUTO_INCREMENT,
  `list_id` int NOT NULL,
  `row_id` int NOT NULL,
  `column_position` int NOT NULL,
  `value` text,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_cell_per_list` (`list_id`,`row_id`,`column_position`),
  CONSTRAINT `list_data_ibfk_1` FOREIGN KEY (`list_id`) REFERENCES `lists` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=73 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
EOF

    # Replace environment variables in the init.sql file
    sed -i "s/\${DB_NAME}/${DB_NAME}/g" ../app/init.sql
    sed -i "s/\${DB_USER}/${DB_USER}/g" ../app/init.sql
    sed -i "s/\${DB_PASSWORD}/${DB_PASSWORD}/g" ../app/init.sql
    
    # Update generation date
    current_date=$(date)
    sed -i "s/\$(date)/${current_date}/g" ../app/init.sql
    
    print_message "init.sql file created successfully with the integrated database structure"
}


# Help function to display script usage
show_usage() {
    echo "Usage: $0 [OPTION]"
    echo ""
    echo "Options:"
    echo "  start       Start containers"
    echo "  stop        Stop containers"
    echo "  help, -h, --help  Display this help message"
    echo "  (none)      Display the interactive menu"
    echo ""
}

# Check if arguments were passed to the script
if [ $# -gt 0 ]; then
    case "$1" in
        start)
            start_containers
            reset_variables
            exit 0
            ;;
        stop)
            stop_containers
            exit 0
            ;;
        help|-h|--help)
            show_usage
            exit 0
            ;;
        *)
            print_error "Invalid option: $1"
            show_usage
            exit 1
            ;;
    esac
fi

# Main menu (if no arguments are passed)
echo "==================================================="
echo "      List-IQ Installation"
echo "==================================================="
echo ""
echo "This script will help you configure and install"
echo "the List-IQ application."
echo ""
echo "Available options:"
echo "1. Configure the installation"
echo "2. Start containers"
echo "3. Stop containers"
echo "4. Reset installation variables"
echo "5. Exit"
echo ""

read -p "Choose an option (1-5): " option

case $option in
    1)
        configure_installation
        # Check if NEW_INSTALL is set to true or false
        if grep -q "NEW_INSTALL=true" .env; then
            print_message "New installation detected, generating init.sql file..."
            generate_init_sql
        else
            print_message "No new installation, clearing the content of init.sql file..."
            clear_init_sql
        fi
        ;;
    2)
        start_containers
        reset_variables
        ;;
    3)
        stop_containers
        ;;
    4)
        reset_variables
        ;;
    5)
        print_message "Goodbye!"
        exit 0
        ;;
    *)
        print_error "Invalid option"
        exit 1
        ;;
esac

print_message "Operation completed successfully"