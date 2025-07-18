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
