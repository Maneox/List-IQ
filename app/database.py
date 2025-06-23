from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

# Create unique instances
db = SQLAlchemy()
csrf = CSRFProtect()