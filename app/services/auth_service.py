from models.user import User
from models.ldap_config import LDAPConfig
from services.ldap_service import LDAPService
from database import db
import os
import logging
import ldap

logger = logging.getLogger(__name__)

class AuthService:
    @staticmethod
    def get_ldap_config():
        """Gets the active LDAP configuration."""
        try:
            ldap_config = LDAPConfig.query.first()
            if not ldap_config:
                logger.error("No LDAP configuration found in the database")
                return None
                
            if not ldap_config.enabled:
                logger.info("LDAP authentication is disabled")
                return None
                
            return ldap_config
        except Exception as e:
            logger.error(f"Error getting LDAP configuration: {str(e)}")
            return None
    
    @staticmethod
    def authenticate_local(username, password):
        user = User.query.filter_by(username=username, auth_type='local').first()
        if user and user.check_password(password):
            return user
        return None
    
    @staticmethod
    def authenticate_ldap(username, password):
        """Authenticates a user via LDAP using sAMAccountName."""
        try:
            logger.info(f"Attempting LDAP authentication for user: {username}")
            
            # Import the new LDAPAuth class
            from services.ldap_auth import LDAPAuth
            
            # Authenticate the user with LDAPAuth
            # The method now returns a tuple (user_dn, is_admin)
            auth_result = LDAPAuth.authenticate_user(username, password)
            
            if not auth_result:
                logger.warning(f"LDAP authentication failed for user: {username}")
                return None
                
            user_dn, is_admin = auth_result
            logger.info(f"LDAP authentication successful for user: {username} (DN: {user_dn}, Admin: {is_admin})")
            
            # Directly use the administrator status determined by the group membership check
            
            # Create or update the user in the database
            user = User.query.filter_by(username=username).first()
            if not user:
                user = User(username=username, is_admin=is_admin, auth_type='ldap')
                db.session.add(user)
                logger.info(f"New LDAP user created: {username}, admin: {is_admin}")
            else:
                user.is_admin = is_admin
                user.auth_type = 'ldap'
                logger.info(f"Existing LDAP user updated: {username}, admin: {is_admin}")
            
            db.session.commit()
            logger.info(f"User {username} created/updated in the database successfully")
            
            return user
            
        except Exception as e:
            logger.error(f"Error during LDAP authentication: {str(e)}")
            logger.exception(e)  # Log the full exception with traceback
            return None
            
    @staticmethod
    def is_user_in_group(user_dn, group_dn, ldap_config):
        """Checks if the user is a member of a specific group."""
        try:
            ldap_service = LDAPService()
            conn = ldap_service.get_ldap_connection(ldap_config)
            if not conn:
                logger.error("Could not establish an LDAP connection to check group membership")
                return False

            # If the group is empty or None, we consider that the user does not need to be in a specific group
            if not group_dn or group_dn.strip() == "":
                logger.info(f"No group specified for verification. Access granted by default.")
                return True

            # Get the group
            group_filter = f"(&(objectClass={ldap_config.group_object_class})(distinguishedName={group_dn}))"
            logger.info(f"Group search filter: {group_filter}")
            
            group_results = conn.search_s(
                ldap_config.base_dn,
                ldap.SCOPE_SUBTREE,
                group_filter,
                [ldap_config.group_member_attr]
            )

            if not group_results:
                logger.warning(f"Group {group_dn} not found")
                # If the group does not exist but was specified, access is denied
                return False

            group_dn, group_attrs = group_results[0]
            logger.info(f"Group found: {group_dn}")
            
            # Check if the user is a member of the group
            if ldap_config.group_member_attr in group_attrs:
                members = group_attrs[ldap_config.group_member_attr]
                logger.info(f"Member attribute found: {ldap_config.group_member_attr}")
                logger.info(f"Number of members in the group: {len(members)}")
                
                # Convert to a list of strings if necessary
                members = [m.decode('utf-8') if isinstance(m, bytes) else m for m in members]
                
                # Check if the user is in the list of members
                is_member = False
                
                # Ensure user_dn is not None
                if user_dn is None:
                    logger.warning("User's DN is None, cannot check group membership")
                    return False
                    
                for member in members:
                    if member is None:
                        continue
                        
                    try:
                        if user_dn.lower() == member.lower():
                            is_member = True
                            break
                        # Sometimes the DN can be formatted differently, check if the username is present
                        if ',' in user_dn and member.lower():
                            if user_dn.split(',')[0].lower() in member.lower():
                                is_member = True
                                logger.info(f"Partial match found: {user_dn.split(',')[0]} in {member}")
                                break
                    except (AttributeError, TypeError) as e:
                        logger.warning(f"Error comparing members: {str(e)}")
                        continue
                
                if is_member:
                    logger.info(f"User {user_dn} is a member of group {group_dn}")
                    return True
                else:
                    logger.warning(f"User {user_dn} is not a member of group {group_dn}")
            else:
                logger.warning(f"Member attribute {ldap_config.group_member_attr} not found in group {group_dn}")

            return False

        except Exception as e:
            logger.error(f"Error checking group membership: {str(e)}")
            logger.exception(e)  # Log the full exception with traceback
            return False
            
    @staticmethod
    def create_user(username, password, is_admin=False, auth_type='local'):
        user = User(username=username, is_admin=is_admin, auth_type=auth_type)
        if auth_type == 'local':
            user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user