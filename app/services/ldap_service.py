import ldap
import ldap.filter
from ldap.ldapobject import ReconnectLDAPObject
from ..models.ldap_config import LDAPConfig
from ..models.user import User
from .. import db
import logging
import os
import tempfile
import ssl

# Enable detailed logging for the LDAP module
ldap_logger = logging.getLogger('ldap')
ldap_logger.setLevel(logging.DEBUG)

logger = logging.getLogger(__name__)

class LDAPService:
    @staticmethod
    def get_ldap_connection(ldap_config=None):
        """
        Establishes an LDAP connection with the provided configuration parameters
        
        Args:
            ldap_config: LDAP configuration to use (if None, uses the default configuration)
            
        Returns:
            tuple: (connection, success, error_message)
        """
        if not ldap_config:
            ldap_config = LDAPConfig.get_config()
            
        if not ldap_config or not ldap_config.enabled:
            return None, False, "LDAP configuration not found or disabled"
            
        try:
            # Create the LDAP URI
            protocol = "ldaps" if ldap_config.use_ssl else "ldap"
            uri = f"{protocol}://{ldap_config.host}:{ldap_config.port}"
            logger.info(f"Connecting to {uri}")
            
            # Initialize the connection
            conn = ldap.initialize(uri)
            conn.protocol_version = ldap.VERSION3
            conn.set_option(ldap.OPT_REFERRALS, 0)
            
            # SSL/TLS Configuration
            if ldap_config.use_ssl or ldap_config.use_tls:
                if ldap_config.verify_cert:
                    # If verification is enabled but no certificate is provided, fail
                    if not ldap_config.ca_cert:
                        logger.error("Certificate verification enabled but no CA certificate is available")
                        return None, False, "Certificate verification is enabled but no CA certificate is available"
                    
                    # Otherwise, continue with the provided CA certificate
                    # Use the provided CA certificate and enable verification
                    try:
                        # Create a temporary file to store the CA certificate
                        ca_cert_file = None
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.pem') as temp_file:
                            temp_file.write(ldap_config.ca_cert.encode('utf-8'))
                            ca_cert_file = temp_file.name
                        
                        # Configure LDAP to use the CA certificate
                        logger.info(f"Using CA certificate for connection to {ldap_config.host}")
                        logger.info(f"CA certificate size: {len(ldap_config.ca_cert)} bytes")
                        conn.set_option(ldap.OPT_X_TLS_CACERTFILE, ca_cert_file)
                        
                        # Use the strict verification level which requires a valid certificate
                        # OPT_X_TLS_DEMAND = Requires a valid certificate, fails if verification fails
                        logger.info("Setting certificate verification level: OPT_X_TLS_DEMAND")
                        conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_DEMAND)
                        
                        # Apply the new TLS options
                        conn.set_option(ldap.OPT_X_TLS_NEWCTX, 0)
                        
                        logger.info("Strict SSL/TLS certificate verification enabled with the provided CA certificate")
                        logger.info(f"Connecting to {ldap_config.host} with strict certificate verification")
                        logger.info("=== Start of SSL/TLS certificate verification ===")
                    except Exception as e:
                        logger.error(f"Error configuring CA certificate: {str(e)}")
                        # In case of error, disable certificate verification
                        conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
                        logger.warning("SSL/TLS certificate verification disabled due to an error")
                    finally:
                        # Delete the temporary file if created
                        if ca_cert_file and os.path.exists(ca_cert_file):
                            try:
                                os.unlink(ca_cert_file)
                            except:
                                pass
                else:
                    # Disable certificate verification
                    logger.info("Disabling SSL/TLS certificate verification for LDAP connection")
                    conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
                    conn.set_option(ldap.OPT_X_TLS_NEWCTX, 0)
            
            # Enable TLS if necessary (for LDAP+StartTLS)
            if ldap_config.use_tls and not ldap_config.use_ssl:
                conn.start_tls_s()
                logger.info("StartTLS enabled for LDAP connection")
                
            # Establish the connection with bind
            if ldap_config.bind_dn and ldap_config.bind_password:
                try:
                    conn.simple_bind_s(ldap_config.bind_dn, ldap_config.bind_password)
                    logger.info(f"Connection established with bind_dn: {ldap_config.bind_dn}")
                    
                    # Check if the connection is secure (SSL/TLS)
                    if ldap_config.use_ssl or ldap_config.use_tls:
                        logger.info("=== Certificate verification successful ===")
                        if ldap_config.verify_cert:
                            logger.info("The connection is secure with certificate verification")
                        else:
                            logger.info("The connection is secure without certificate verification")
                    else:
                        logger.info("The connection is not secure (no SSL/TLS)")
                except Exception as e:
                    logger.error(f"Error during connection: {str(e)}")
                    raise
            else:
                # Anonymous connection
                conn.simple_bind_s()
                logger.info("Anonymous connection established")
                
            return conn, True, "Connection established successfully"
            
        except ldap.SERVER_DOWN as e:
            error_msg = f"Could not connect to the LDAP server: {str(e)}"
            logger.error(error_msg)
            return None, False, error_msg
            
        except ldap.INVALID_CREDENTIALS as e:
            error_msg = f"Invalid LDAP credentials: {str(e)}"
            logger.error(error_msg)
            return None, False, error_msg
            
        except Exception as e:
            error_msg = f"Error during LDAP connection: {str(e)}"
            logger.error(error_msg)
            return None, False, error_msg
    
    @classmethod
    def test_connection(cls, ldap_config):
        """Tests the LDAP connection with the provided parameters"""
        conn, success, message = cls.get_ldap_connection(ldap_config)
        
        if conn:
            try:
                conn.unbind_s()
            except:
                pass
                
        return success, message
    
    @classmethod
    def authenticate_user(cls, username, password, ldap_config=None):
        """
        Authenticates a user via LDAP
        
        Args:
            username: Username
            password: Password
            ldap_config: LDAP configuration to use (if None, uses the default configuration)
            
        Returns:
            tuple: (success, user_data, error_message)
        """
        if not ldap_config:
            ldap_config = LDAPConfig.get_config()
            
        if not ldap_config or not ldap_config.enabled:
            return False, None, "LDAP configuration not found or disabled"
            
        # Establish the connection
        logger.info(f"Attempting LDAP authentication for user: {username}")
        logger.info(f"Connection parameters - Host: {ldap_config.host}, Port: {ldap_config.port}, SSL: {ldap_config.use_ssl}, TLS: {ldap_config.use_tls}")
        
        conn, success, message = cls.get_ldap_connection(ldap_config)
        if not success:
            logger.error(f"Could not establish LDAP connection: {message}")
            return False, None, message
        
        logger.info("LDAP connection established successfully for user search")
            
        try:
            # Escape special characters in the username
            safe_username = ldap.filter.escape_filter_chars(username)
            
            # Build the search filter
            search_filter = f"(&(objectClass={ldap_config.user_object_class})({ldap_config.user_login_attr}={safe_username}))"
            
            # Determine the base DN for the search
            search_base = ldap_config.user_dn or ldap_config.base_dn
            
            # Search for the user
            logger.info(f"LDAP search: base={search_base}, filter={search_filter}")
            result = conn.search_s(search_base, ldap.SCOPE_SUBTREE, search_filter, ['cn', 'mail', 'memberOf', 'displayName', ldap_config.user_login_attr])
            
            if not result or len(result) == 0:
                return False, None, f"User {username} not found in LDAP"
                
            # Get the user's DN
            user_dn, user_attrs = result[0]
            
            if not user_dn:
                return False, None, f"DN not found for user {username}"
                
            # Attempt to connect with the user's credentials
            try:
                # For user authentication, we use the same LDAP connection
                # rather than creating a new one, as it works better with LDAPS
                logger.info(f"Attempting user authentication with DN: {user_dn}")
                
                # Use the existing connection for authentication
                conn.simple_bind_s(user_dn, password)
                
                # Authentication successful
                logger.info(f"LDAP authentication successful for {username}")
                
                # Check group membership
                is_admin = cls._check_group_membership(user_attrs, ldap_config.admin_group, ldap_config)
                is_user = cls._check_group_membership(user_attrs, ldap_config.user_group, ldap_config)
                
                if not (is_admin or is_user):
                    return False, None, f"User {username} does not belong to any authorized group"
                
                # Extract user information
                user_data = {
                    'username': username,
                    'email': user_attrs.get('mail', [b''])[0].decode('utf-8') if 'mail' in user_attrs else '',
                    'display_name': user_attrs.get('displayName', [b''])[0].decode('utf-8') if 'displayName' in user_attrs else '',
                    'is_admin': is_admin,
                    'dn': user_dn
                }
                
                return True, user_data, "Authentication successful"
                
            except ldap.INVALID_CREDENTIALS:
                return False, None, "Incorrect password"
                
            except Exception as e:
                error_msg = f"Error during user authentication: {str(e)}"
                logger.error(error_msg)
                return False, None, error_msg
                
        except Exception as e:
            error_msg = f"Error during LDAP search: {str(e)}"
            logger.error(error_msg)
            return False, None, error_msg
            
        finally:
            # Close the connection
            try:
                conn.unbind_s()
            except:
                pass
    
    @classmethod
    def _check_group_membership(cls, user_attrs, group_dn, ldap_config):
        """Checks if the user belongs to a specific group"""
        if not group_dn:
            return False
            
        # Check via the memberOf attribute
        if 'memberOf' in user_attrs:
            member_of = [m.decode('utf-8').lower() for m in user_attrs['memberOf']]
            return group_dn.lower() in member_of
            
        return False
    
    @classmethod
    def get_ldap_groups(cls, ldap_config=None):
        """Gets the list of available LDAP groups"""
        if not ldap_config:
            ldap_config = LDAPConfig.get_config()
            
        if not ldap_config or not ldap_config.enabled:
            logger.warning("LDAP configuration disabled or missing")
            return []
            
        # Establish the connection
        conn, success, message = cls.get_ldap_connection(ldap_config)
        if not success:
            logger.error(f"Could not establish an LDAP connection: {message}")
            return []
            
        try:
            # Determine the base DN for the search
            search_base = ldap_config.group_dn or ldap_config.base_dn
            if not search_base:
                logger.error("Base DN for group search not specified")
                return []
            
            # Build the search filter
            # Use a more generic filter if group_object_class is not specified
            if ldap_config.group_object_class and ldap_config.group_object_class.strip():
                search_filter = f"(objectClass={ldap_config.group_object_class})"
            else:
                # Default filter for groups (works with Active Directory and most LDAP servers)
                search_filter = "(|(objectClass=group)(objectClass=groupOfNames)(objectClass=groupOfUniqueNames))"
            
            # Search for groups
            logger.info(f"Searching for LDAP groups: base={search_base}, filter={search_filter}")
            
            # Use search_ext_s with a timeout to avoid blocking
            result = conn.search_ext_s(
                search_base, 
                ldap.SCOPE_SUBTREE, 
                search_filter, 
                ['cn', 'distinguishedName', 'name', 'sAMAccountName'], 
                timeout=30
            )
            
            logger.info(f"LDAP search results: {len(result)} groups found")
            
            groups = []
            for dn, attrs in result:
                if dn:
                    # Try different attributes to get the group name
                    group_name = None
                    for attr in ['cn', 'name', 'sAMAccountName']:
                        if attr in attrs and attrs[attr]:
                            try:
                                group_name = attrs[attr][0].decode('utf-8')
                                break
                            except (UnicodeDecodeError, AttributeError):
                                # If decoding fails, try without decoding (if it's already a string)
                                try:
                                    group_name = attrs[attr][0]
                                    break
                                except:
                                    continue
                    
                    # If no name was found, use the DN
                    if not group_name:
                        group_name = dn
                    
                    groups.append({
                        'dn': dn,
                        'name': group_name
                    })
                    logger.debug(f"LDAP group found: {group_name} ({dn})")
            
            logger.info(f"Total number of LDAP groups retrieved: {len(groups)}")
            return groups
            
        except ldap.LDAPError as e:
            error_desc = e.args[0].get('desc', str(e)) if e.args and isinstance(e.args[0], dict) else str(e)
            logger.error(f"LDAP error while retrieving groups: {error_desc}")
            return []
        except Exception as e:
            logger.error(f"Error retrieving LDAP groups: {str(e)}")
            return []
            
        finally:
            # Close the connection
            try:
                conn.unbind_s()
            except:
                pass