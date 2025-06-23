from database import db
from datetime import datetime

class LDAPConfig(db.Model):
    """Model for storing LDAP configuration"""
    id = db.Column(db.Integer, primary_key=True)
    
    # Connection parameters
    enabled = db.Column(db.Boolean, default=False)
    host = db.Column(db.String(255), nullable=True)
    port = db.Column(db.Integer, default=389)
    use_ssl = db.Column(db.Boolean, default=False)
    use_tls = db.Column(db.Boolean, default=False)
    ca_cert = db.Column(db.Text, nullable=True)  # CA certificate in PEM format
    verify_cert = db.Column(db.Boolean, default=False)  # SSL/TLS certificate verification
    
    # Authentication parameters
    bind_dn = db.Column(db.String(255), nullable=True)
    bind_password = db.Column(db.String(255), nullable=True)
    
    # Search parameters
    base_dn = db.Column(db.String(255), nullable=True)
    user_dn = db.Column(db.String(255), nullable=True)
    group_dn = db.Column(db.String(255), nullable=True)
    user_rdn_attr = db.Column(db.String(64), default='sAMAccountName')
    user_login_attr = db.Column(db.String(64), default='sAMAccountName')
    user_object_class = db.Column(db.String(64), default='person')
    
    # Authorization parameters
    admin_group = db.Column(db.String(255), nullable=True)
    user_group = db.Column(db.String(255), nullable=True)
    group_member_attr = db.Column(db.String(64), default='member')
    group_object_class = db.Column(db.String(64), default='group')
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @classmethod
    def get_config(cls):
        """Retrieves the active LDAP configuration or creates a new one if it doesn't exist"""
        config = cls.query.first()
        if not config:
            config = cls()
            db.session.add(config)
            db.session.commit()
        return config
    
    def to_dict(self):
        """Converts the object to a dictionary"""
        return {
            'id': self.id,
            'enabled': self.enabled,
            'host': self.host,
            'port': self.port,
            'use_ssl': self.use_ssl,
            'use_tls': self.use_tls,
            'bind_dn': self.bind_dn,
            'bind_password': '********' if self.bind_password else None,
            'base_dn': self.base_dn,
            'user_dn': self.user_dn,
            'group_dn': self.group_dn,
            'user_rdn_attr': self.user_rdn_attr,
            'user_login_attr': self.user_login_attr,
            'user_object_class': self.user_object_class,
            'admin_group': self.admin_group,
            'user_group': self.user_group,
            'group_member_attr': self.group_member_attr,
            'group_object_class': self.group_object_class,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }