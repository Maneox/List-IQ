from database import db
from datetime import datetime, timezone

class ListColumn(db.Model):
    """Model for list columns"""
    __tablename__ = 'list_columns'

    id = db.Column(db.Integer, primary_key=True)
    list_id = db.Column(db.Integer, db.ForeignKey('lists.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    position = db.Column(db.Integer, nullable=False)
    column_type = db.Column(db.String(50), nullable=False, default='text')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc)) # Use lambda for default

    def __init__(self, **kwargs):
        # Default created_at is handled by db.Column default.
        # Explicitly set if not provided, or rely on default.
        if 'created_at' not in kwargs:
            kwargs['created_at'] = datetime.now(timezone.utc)
        if 'column_type' not in kwargs or not kwargs['column_type']: # Ensure column_type is not empty
            kwargs['column_type'] = 'text'
        super(ListColumn, self).__init__(**kwargs)

    __table_args__ = (
        db.UniqueConstraint('list_id', 'name', name='unique_name_per_list'),
        db.UniqueConstraint('list_id', 'position', name='unique_position_per_list')
    )

class ListData(db.Model):
    __tablename__ = 'list_data'

    id = db.Column(db.Integer, primary_key=True)
    list_id = db.Column(db.Integer, db.ForeignKey('lists.id'), nullable=False)
    row_id = db.Column(db.Integer, nullable=False) # Represents the row number within a list's dataset
    column_position = db.Column(db.Integer, nullable=False) # Links to ListColumn.position
    value = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('list_id', 'row_id', 'column_position', # Swapped row_id and column_position for typical query patterns
                           name='unique_cell_per_list'),
    )

    def __repr__(self):
        return f"<ListData(id={self.id}, list_id={self.list_id}, row_id={self.row_id}, " \
               f"column_position={self.column_position}, value='{str(self.value)[:30]}...')>" # Shortened value