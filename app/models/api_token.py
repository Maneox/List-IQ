from database import db
from datetime import datetime

class ApiToken(db.Model):
    """
    Model for API tokens used for authentication.
    """
    __tablename__ = 'api_tokens'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)  # Descriptive name for the token
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)  # NULL means no expiration
    last_used_at = db.Column(db.DateTime, nullable=True)
    
    # The relationship is now defined on the User side with cascade
    
    def __repr__(self):
        return f'<ApiToken {self.name}>'
    
    def to_dict(self):
        """
        Converts the token to a dictionary for API responses.
        Never returns the token value for security reasons.
        """
        return {
            'id': self.id,
            'name': self.name,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None
        }
    
    def is_expired(self):
        """
        Checks if the token has expired.
        
        Returns:
            bool: True if the token is expired, False otherwise.
        """
        if not self.expires_at:
            return False
        return self.expires_at < datetime.utcnow()