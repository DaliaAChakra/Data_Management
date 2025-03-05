from django.db import connection
import csv
from .models import TableSchema, FieldSchema


ALLOWED_COLUMN_TYPES = {"TEXT", "INTEGER", "BOOLEAN", "DATE", "TIMESTAMP"}


def is_valid_table(table_name):
    """Ensure table exists in the TableSchema model."""
    from .models import TableSchema 
    return TableSchema.objects.filter(name=table_name).exists()


def validate_fields(fields):
    """Check that field names are valid and types are allowed."""
    return all(field["name"].isidentifier() and field["type"].upper() in ALLOWED_COLUMN_TYPES for field in fields)


def create_table_service(table_name, fields):
    """Service to create a table dynamically"""
    if not table_name:
        raise ValueError("Table name is required")
    
    if not fields:
        raise ValueError("Fields are required")

    query = f"""
    SELECT EXISTS (
        SELECT 1
        FROM information_schema.tables 
        WHERE table_name = '{table_name}'
    );
    """
    with connection.cursor() as cursor:
        cursor.execute(query)
        table_exists = cursor.fetchone()[0] 

    if table_exists:
        raise ValueError(f'Table "{table_name}" already exists')

    columns = 'id SERIAL PRIMARY KEY, created_at TIMESTAMP DEFAULT NOW()'
    
    for field in fields:
        field_name = field.get("name")
        field_type = field.get("type")
        is_unique = field.get("is_unique", False) 

        if not field_name or not field_type:
            raise ValueError("Each field must have a name and type")

        unique_constraint = " UNIQUE" if is_unique else ""
        columns += f', "{field_name}" {field_type}{unique_constraint}'

    query = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({columns});'
    
    with connection.cursor() as cursor:
        cursor.execute(query)

    table_schema = TableSchema.objects.create(name=table_name)
    for field in fields:
        FieldSchema.objects.create(
            table=table_schema,
            name=field["name"],
            field_type=field["type"],
            is_unique=field.get("is_unique", False)
        )

    return f'Table "{table_name}" created successfully with fields'


def bulk_insert_csv(file_path, table_name):
    """Fast CSV import using PostgreSQL COPY."""
    with connection.cursor() as cursor:
        with open(file_path, 'r', encoding='utf-8') as f:
            cursor.copy_expert(f"COPY {table_name} FROM STDIN WITH CSV HEADER", f)
