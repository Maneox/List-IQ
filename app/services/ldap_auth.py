import ldap
import ldap.filter
from models.ldap_config import LDAPConfig
from models.user import User
from database import db
import logging
import os
import tempfile

logger = logging.getLogger(__name__)

class LDAPAuth:
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
                        conn.set_option(ldap.OPT_X_TLS_CACERTFILE, ca_cert_file)
                        
                        # Use the strict verification level which requires a valid certificate
                        # OPT_X_TLS_DEMAND = Requires a valid certificate, fails if verification fails
                        conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_DEMAND)
                        
                        # Apply the new TLS options
                        conn.set_option(ldap.OPT_X_TLS_NEWCTX, 0)
                        
                        logger.info("Strict SSL/TLS certificate verification enabled with the provided CA certificate")
                        logger.info(f"Connecting to {ldap_config.host} with strict certificate verification")
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
            
            # Enable TLS if necessary
            if ldap_config.use_tls and not ldap_config.use_ssl:
                conn.start_tls_s()
                
            # Establish the connection with bind
            if ldap_config.bind_dn and ldap_config.bind_password:
                conn.simple_bind_s(ldap_config.bind_dn, ldap_config.bind_password)
                logger.info(f"Connection established with bind_dn: {ldap_config.bind_dn}")
            else:
                # Anonymous connection
                conn.simple_bind_s()
                logger.info("Anonymous connection established")
                
            return conn, True, "Connection established successfully"
            
        except ldap.SERVER_DOWN:
            return None, False, "LDAP server unreachable"
        except ldap.INVALID_CREDENTIALS:
            return None, False, "Invalid connection credentials"
        except ldap.LDAPError as e:
            return None, False, f"LDAP error: {str(e)}"
        except Exception as e:
            return None, False, f"Unexpected error: {str(e)}"
    
    @classmethod
    def authenticate_user(cls, username, password):
        """
        Authenticates a user via LDAP using sAMAccountName
        
        Args:
            username: Username (sAMAccountName)
            password: Password
            
        Returns:
            tuple or None: (User's DN, is_admin) or None if failed
        """
        logger.info(f"Attempting LDAP authentication for user: {username}")
        ldap_config = LDAPConfig.get_config()
        
        if not ldap_config or not ldap_config.enabled or not ldap_config.host:
            logger.warning("LDAP authentication disabled or host not configured")
            return None
            
        try:
            # Step 1: Connect to the LDAP server with service credentials
            conn, success, error_message = LDAPAuth.get_ldap_connection(ldap_config)
            
            if not success:
                logger.error(f"Failed to connect to the LDAP server: {error_message}")
                return None
                
            # Step 2: Search for the user by sAMAccountName
            # Clean the username (remove domain if present)
            try:
                # Clean the username to avoid LDAP injections
                clean_username = ldap.filter.escape_filter_chars(username)
                
                # Build the search filter to find the user by sAMAccountName
                user_filter = f"(&(objectClass=user)(sAMAccountName={clean_username}))"
                logger.info(f"Searching for user {username} with filter: {user_filter}")
                logger.info(f"Base DN for search: {ldap_config.base_dn}")
                
                # Execute the search with all necessary attributes
                user_results = conn.search_s(
                    ldap_config.base_dn,
                    ldap.SCOPE_SUBTREE,
                    user_filter,
                    ['sAMAccountName', 'memberOf', 'distinguishedName', 'cn']
                )
                
                logger.info(f"Search results for {username}: {len(user_results)} entries found")
                
                if not user_results:
                    logger.warning(f"User {username} not found in LDAP")
                    return None
                elif len(user_results) > 1:
                    logger.warning(f"Multiple entries found for user {username}: {len(user_results)} results")
                    logger.info(f"Using the first entry found")
                    # Display all found entries for debugging
                    for i, (dn, attrs) in enumerate(user_results):
                        logger.info(f"Entry {i+1}: DN={dn}")
                    
                user_dn, user_attrs = user_results[0]
                logger.info(f"LDAP user found: {user_dn}")
                
                # Display user attributes for debugging
                logger.info("User attributes:")
                for attr_name, attr_values in user_attrs.items():
                    decoded_values = [v.decode('utf-8') if isinstance(v, bytes) else v for v in attr_values]
                    logger.info(f"  {attr_name}: {decoded_values}")
                
            except ldap.LDAPError as e:
                logger.error(f"Error searching for user: {str(e)}")
                return None
                
            # Step 3: Authenticate the user with their own DN and password
            try:
                # Create a new connection for user authentication
                protocol = "ldaps" if ldap_config.use_ssl else "ldap"
                uri = f"{protocol}://{ldap_config.host}:{ldap_config.port}"
                user_conn = ldap.initialize(uri)
                user_conn.protocol_version = ldap.VERSION3
                user_conn.set_option(ldap.OPT_REFERRALS, 0)
                
                # SSL/TLS configuration for user authentication
                if ldap_config.use_ssl or ldap_config.use_tls:
                    if ldap_config.verify_cert and ldap_config.ca_cert:
                        # Use the provided CA certificate and enable verification
                        try:
                            # Create a temporary file to store the CA certificate
                            ca_cert_file = None
                            with tempfile.NamedTemporaryFile(delete=False, suffix='.pem') as temp_file:
                                temp_file.write(ldap_config.ca_cert.encode('utf-8'))
                                ca_cert_file = temp_file.name
                            
                            # Configure LDAP to use the CA certificate
                            user_conn.set_option(ldap.OPT_X_TLS_CACERTFILE, ca_cert_file)
                            
                            # Use the least strict verification level while still checking the certificate
                            # OPT_X_TLS_TRY = Checks the certificate if provided, but does not fail if verification fails
                            user_conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_TRY)
                            
                            # Apply the new TLS options
                            user_conn.set_option(ldap.OPT_X_TLS_NEWCTX, 0)
                            
                            logger.info("Flexible SSL/TLS certificate verification enabled with the provided CA certificate for user authentication")
                            logger.info(f"Connecting to {ldap_config.host} with minimal certificate verification for user authentication")
                        except Exception as e:
                            logger.error(f"Error configuring CA certificate for user authentication: {str(e)}")
                            # In case of error, disable certificate verification
                            user_conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
                            logger.warning("SSL/TLS certificate verification disabled due to an error for user authentication")
                        finally:
                            # Delete the temporary file if created
                            if ca_cert_file and os.path.exists(ca_cert_file):
                                try:
                                    os.unlink(ca_cert_file)
                                except:
                                    pass
                    else:
                        # Disable certificate verification
                        logger.info("Disabling SSL/TLS certificate verification for user authentication")
                        user_conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
                        user_conn.set_option(ldap.OPT_X_TLS_NEWCTX, 0)
                
                # Enable TLS if necessary
                if ldap_config.use_tls and not ldap_config.use_ssl:
                    user_conn.start_tls_s()
                    
                # Authenticate the user
                user_conn.simple_bind_s(user_dn, password)
                user_conn.unbind_s()
                
                logger.info(f"Authentication successful for user {username}")
                
                # Step 4: Check membership in configured groups
                is_admin = False
                is_user = False
                
                try:
                    # Get all groups the user is a member of
                    if 'memberOf' in user_attrs:
                        user_groups = user_attrs['memberOf']
                        user_groups = [g.decode('utf-8') if isinstance(g, bytes) else g for g in user_groups]
                        logger.info(f"Groups for user {username}: {user_groups}")
                        
                        # Check if the user is a member of the admin group
                        if ldap_config.admin_group:
                            admin_group_dn = ldap_config.admin_group
                            logger.info(f"Checking if the user is a member of the admin group: {admin_group_dn}")
                            
                            for group_dn in user_groups:
                                if group_dn.lower() == admin_group_dn.lower():
                                    is_admin = True
                                    is_user = True  # An admin is also a user
                                    logger.info(f"User {username} is a member of the admin group")
                                    break
                            
                            if not is_admin:
                                logger.info(f"User {username} is not a member of the admin group")
                        
                        # If the user is not an admin, check if they are a member of the user group
                        if not is_user and ldap_config.user_group:
                            user_group_dn = ldap_config.user_group
                            logger.info(f"Checking if the user is a member of the user group: {user_group_dn}")
                            
                            for group_dn in user_groups:
                                if group_dn.lower() == user_group_dn.lower():
                                    is_user = True
                                    logger.info(f"User {username} is a member of the user group")
                                    break
                            
                            if not is_user:
                                logger.info(f"User {username} is not a member of the user group")
                    else:
                        # If the memberOf attribute is not present, try another approach
                        logger.warning(f"The memberOf attribute is not present for user {username}, using another method")
                        
                        # Check if the user is a member of the admin group
                        if ldap_config.admin_group:
                            logger.info(f"Checking membership in admin group: {ldap_config.admin_group}")
                            admin_group_filter = f"(&(objectClass={ldap_config.group_object_class})(distinguishedName={ldap.filter.escape_filter_chars(ldap_config.admin_group)}))"
                            
                            admin_group_results = conn.search_s(
                                ldap_config.base_dn,
                                ldap.SCOPE_SUBTREE,
                                admin_group_filter,
                                [ldap_config.group_member_attr]
                            )
                            
                            if admin_group_results:
                                admin_group_dn, admin_group_attrs = admin_group_results[0]
                                logger.info(f"Admin group found: {admin_group_dn}")
                                
                                if ldap_config.group_member_attr in admin_group_attrs:
                                    admin_members = admin_group_attrs[ldap_config.group_member_attr]
                                    admin_members = [m.decode('utf-8') if isinstance(m, bytes) else m for m in admin_members]
                                    
                                    logger.info(f"Members of the admin group: {admin_members}")
                                    
                                    for member in admin_members:
                                        if user_dn.lower() == member.lower():
                                            is_admin = True
                                            is_user = True  # An admin is also a user
                                            logger.info(f"User {username} is a member of the admin group")
                                            break
                            else:
                                logger.warning(f"Admin group {ldap_config.admin_group} not found")
                        
                        # If the user is not an admin, check if they are a member of the user group
                        if not is_user and ldap_config.user_group:
                            logger.info(f"Checking membership in user group: {ldap_config.user_group}")
                            user_group_filter = f"(&(objectClass={ldap_config.group_object_class})(distinguishedName={ldap.filter.escape_filter_chars(ldap_config.user_group)}))"
                            
                            user_group_results = conn.search_s(
                                ldap_config.base_dn,
                                ldap.SCOPE_SUBTREE,
                                user_group_filter,
                                [ldap_config.group_member_attr]
                            )
                            
                            if user_group_results:
                                user_group_dn, user_group_attrs = user_group_results[0]
                                logger.info(f"User group found: {user_group_dn}")
                                
                                if ldap_config.group_member_attr in user_group_attrs:
                                    user_members = user_group_attrs[ldap_config.group_member_attr]
                                    user_members = [m.decode('utf-8') if isinstance(m, bytes) else m for m in user_members]
                                    
                                    logger.info(f"Members of the user group: {user_members}")
                                    
                                    for member in user_members:
                                        if user_dn.lower() == member.lower():
                                            is_user = True
                                            logger.info(f"User {username} is a member of the user group")
                                            break
                                    
                                    if not is_user:
                                        logger.warning(f"User {username} is not a member of user group {user_group_dn}")
                            else:
                                logger.warning(f"User group {ldap_config.user_group} not found")
                    
                    # If no group is configured, consider the user as a standard user
                    if not ldap_config.admin_group and not ldap_config.user_group:
                        logger.info("No group configured, the user is considered a standard user")
                        is_user = True
                        
                    # Save the result of the group check
                    logger.info(f"Result of group check for {username}: admin={is_admin}, user={is_user}")
                    
                    # If the user does not belong to any authorized group, deny access
                    if not is_admin and not is_user:
                        logger.warning(f"User {username} does not belong to any authorized group, access denied")
                        return None
                        
                except ldap.LDAPError as e:
                    logger.error(f"Error checking group membership: {str(e)}")
                    # Do not block authentication in case of group check error
                
                # Return the user's DN and their admin status
                return user_dn, is_admin
                
            except ldap.INVALID_CREDENTIALS:
                logger.warning(f"Authentication failed for user {username}")
                return None
            except ldap.LDAPError as e:
                logger.error(f"Error during user authentication: {str(e)}")
                return None
                
        except Exception as e:
            logger.error(f"Error during LDAP authentication: {str(e)}")
            logger.exception(e)
            return None
        finally:
            if 'conn' in locals() and conn:
                try:
                    conn.unbind_s()
                except:
                    pass