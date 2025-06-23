from app import create_app, db
from models.user import User
import logging
import time
import os
from dotenv import load_dotenv
from sqlalchemy.exc import OperationalError

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_admin_user():
    app = create_app()
    
    # Retry several times in case of database connection failure
    max_retries = 5
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            with app.app_context():
                # Check if the users table exists
                try:
                    # Check if the admin user already exists
                    admin = User.query.filter_by(username='admin').first()
                    if not admin:
                        # Create the admin user with email to avoid missing column error
                        admin_username = os.getenv('ADMIN_USERNAME', 'admin')
                        admin_email = os.getenv('ADMIN_EMAIL', 'admin@example.com')
                        admin_password = os.getenv('ADMIN_PASSWORD', 'admin')
                        
                        admin = User(username=admin_username, email=admin_email, is_admin=True, auth_type='local')
                        admin.set_password(admin_password)
                        db.session.add(admin)
                        db.session.commit()
                        logger.info("Admin user created successfully")
                    else:
                        # Update the existing admin's password with the values from environment variables
                        admin_username = os.getenv('ADMIN_USERNAME', 'admin')
                        admin_email = os.getenv('ADMIN_EMAIL', 'admin@example.com')
                        admin_password = os.getenv('ADMIN_PASSWORD', 'admin')
                        
                        # Check if the username needs to be updated
                        if admin.username != admin_username:
                            admin.username = admin_username
                            logger.info(f"Admin username updated to {admin_username}")
                            
                        # Update the password
                        admin.set_password(admin_password)
                        logger.info(f"Admin password updated for user {admin_username}")
                        
                        # Update the email if necessary
                        if not admin.email or admin.email != admin_email:
                            admin.email = admin_email
                            logger.info(f"Admin email updated to {admin_email}")
                            
                        db.session.commit()
                        logger.info("Admin user updated successfully")
                    
                    # If we get here, everything went well
                    return
                except Exception as e:
                    logger.error(f"Error creating/updating admin user: {str(e)}")
                    raise
        except OperationalError as e:
            retry_count += 1
            logger.warning(f"Database connection error (attempt {retry_count}/{max_retries}): {str(e)}")
            if retry_count < max_retries:
                # Wait before retrying
                time.sleep(3)
            else:
                logger.error("Maximum retry attempts reached. Could not connect to database.")
                raise
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            raise

if __name__ == '__main__':
    create_admin_user()