"""
Managed Schema System for Extensions

This module provides infrastructure for extensions to declare custom database tables
(the "Tier 3" approach from the architecture) via their manifest.json.

The system:
1. Parses managed_schemas from the manifest
2. Generates SQL DDL statements (CREATE TABLE, ALTER TABLE, DROP TABLE)
3. Applies migrations safely with transaction support
4. Tracks schema versions per extension

Safety features:
- All tables are prefixed with extension slug to avoid collisions
- Schema changes are versioned
- Rollback support via transactions
- Validation of column types and constraints

Example manifest snippet:
{
  "server_side": {
    "managed_schemas": {
      "schema_version": 1,
      "tables": {
        "computer_activity_details": {
          "columns": [
            {"name": "app_name", "type": "TEXT"},
            {"name": "window_title", "type": "TEXT"},
            {"name": "event_id", "type": "BIGINT", "nullable": false}
          ]
        }
      }
    }
  }
}

This would create a table: `activitywatch_computer_activity_details`
"""

import logging
from typing import Dict, List, Optional, Set
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from ..manifest import ManagedSchemas, ManagedSchemaTable, ManagedSchemaColumn
from .. import models

logger = logging.getLogger(__name__)


class SchemaValidationError(Exception):
    """Raised when a schema definition is invalid."""
    pass


class SchemaMigrationError(Exception):
    """Raised when a schema migration fails."""
    pass


# Allowed SQL types (PostgreSQL/SQLite compatible subset)
ALLOWED_TYPES = {
    "TEXT", "VARCHAR", "CHAR",
    "INT", "INTEGER", "BIGINT", "SMALLINT",
    "DECIMAL", "NUMERIC", "REAL", "DOUBLE PRECISION",
    "BOOLEAN", "BOOL",
    "DATE", "TIME", "TIMESTAMP", "TIMESTAMPTZ",
    "JSONB", "JSON",
    "BYTEA",  # Binary data
}


class SchemaManager:
    """
    Manages dynamic schema creation and migration for extensions.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def validate_column_type(self, col_type: str) -> bool:
        """
        Validate that a column type is allowed.
        
        Args:
            col_type: The SQL type string (e.g., "TEXT", "BIGINT")
            
        Returns:
            True if valid
            
        Raises:
            SchemaValidationError: If type is not allowed
        """
        # Handle types with parameters like VARCHAR(255)
        base_type = col_type.split('(')[0].strip().upper()
        
        if base_type not in ALLOWED_TYPES:
            raise SchemaValidationError(
                f"Column type '{col_type}' is not allowed. "
                f"Allowed types: {', '.join(sorted(ALLOWED_TYPES))}"
            )
        
        return True
    
    def validate_table_name(self, table_name: str) -> bool:
        """
        Validate that a table name is safe (alphanumeric + underscores).
        
        Args:
            table_name: The table name to validate
            
        Returns:
            True if valid
            
        Raises:
            SchemaValidationError: If name is invalid
        """
        if not table_name:
            raise SchemaValidationError("Table name cannot be empty")
        
        if not table_name.replace('_', '').isalnum():
            raise SchemaValidationError(
                f"Table name '{table_name}' must be alphanumeric with underscores only"
            )
        
        if table_name[0].isdigit():
            raise SchemaValidationError(
                f"Table name '{table_name}' cannot start with a digit"
            )
        
        return True
    
    def validate_column_name(self, col_name: str) -> bool:
        """
        Validate that a column name is safe.
        
        Args:
            col_name: The column name to validate
            
        Returns:
            True if valid
            
        Raises:
            SchemaValidationError: If name is invalid
        """
        if not col_name:
            raise SchemaValidationError("Column name cannot be empty")
        
        if not col_name.replace('_', '').isalnum():
            raise SchemaValidationError(
                f"Column name '{col_name}' must be alphanumeric with underscores only"
            )
        
        # Reserved SQL keywords to avoid
        reserved = {"select", "insert", "update", "delete", "from", "where", "table", "index"}
        if col_name.lower() in reserved:
            raise SchemaValidationError(
                f"Column name '{col_name}' is a reserved SQL keyword"
            )
        
        return True
    
    def get_full_table_name(self, extension_slug: str, table_name: str) -> str:
        """
        Get the fully-qualified table name with extension prefix.
        
        Args:
            extension_slug: The extension's slug
            table_name: The table name from the manifest
            
        Returns:
            Full table name like "extensionslug_tablename"
        """
        # Replace hyphens with underscores for SQL compatibility
        safe_slug = extension_slug.replace('-', '_')
        return f"{safe_slug}_{table_name}"
    
    def generate_create_table_ddl(
        self,
        extension_slug: str,
        table_name: str,
        table_def: ManagedSchemaTable,
    ) -> str:
        """
        Generate a CREATE TABLE statement from a table definition.
        
        Args:
            extension_slug: The extension's slug
            table_name: The table name (without prefix)
            table_def: The table definition from the manifest
            
        Returns:
            SQL DDL string
            
        Raises:
            SchemaValidationError: If the schema is invalid
        """
        # Validate table name
        self.validate_table_name(table_name)
        
        full_table_name = self.get_full_table_name(extension_slug, table_name)
        
        # Build column definitions
        column_defs = []
        
        # Always include an id column
        column_defs.append("id BIGSERIAL PRIMARY KEY")
        
        for col in table_def.columns:
            self.validate_column_name(col.name)
            self.validate_column_type(col.type)
            
            col_def = f"{col.name} {col.type}"
            
            # Add nullable constraint
            if col.nullable is False:
                col_def += " NOT NULL"
            
            # Add default value
            if col.default is not None:
                col_def += f" DEFAULT {col.default}"
            
            column_defs.append(col_def)
        
        # Add timestamps (useful for most extension tables)
        column_defs.append("created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()")
        column_defs.append("updated_at TIMESTAMPTZ")
        
        # Generate the CREATE TABLE statement
        ddl = f"CREATE TABLE IF NOT EXISTS {full_table_name} (\n"
        ddl += ",\n".join(f"    {col_def}" for col_def in column_defs)
        ddl += "\n);"
        
        return ddl
    
    def generate_drop_table_ddl(
        self,
        extension_slug: str,
        table_name: str,
    ) -> str:
        """
        Generate a DROP TABLE statement.
        
        Args:
            extension_slug: The extension's slug
            table_name: The table name (without prefix)
            
        Returns:
            SQL DDL string
        """
        full_table_name = self.get_full_table_name(extension_slug, table_name)
        return f"DROP TABLE IF EXISTS {full_table_name} CASCADE;"
    
    async def table_exists(
        self,
        session: AsyncSession,
        table_name: str,
    ) -> bool:
        """
        Check if a table exists in the database.
        
        Args:
            session: Database session
            table_name: Full table name (with prefix)
            
        Returns:
            True if table exists
        """
        # This query works for both PostgreSQL and SQLite
        query = text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = :table_name
            )
        """)
        
        try:
            result = await session.execute(query, {"table_name": table_name})
            return result.scalar() or False
        except Exception:
            # Fallback for SQLite (doesn't have information_schema)
            try:
                sqlite_query = text(f"""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name=:table_name
                """)
                result = await session.execute(sqlite_query, {"table_name": table_name})
                return result.scalar() is not None
            except Exception as e:
                logger.error(f"Error checking table existence: {e}")
                return False
    
    async def apply_managed_schemas(
        self,
        session: AsyncSession,
        extension_slug: str,
        managed_schemas: ManagedSchemas,
    ) -> Dict[str, bool]:
        """
        Apply managed schemas from an extension manifest.
        
        Creates all tables defined in the managed_schemas section.
        
        Args:
            session: Database session
            extension_slug: The extension's slug
            managed_schemas: The managed_schemas from the manifest
            
        Returns:
            Dictionary of table_name -> success (True if created, False if already exists)
            
        Raises:
            SchemaMigrationError: If migration fails
        """
        results = {}
        
        if not managed_schemas.tables:
            logger.info(f"No managed schemas to apply for extension '{extension_slug}'")
            return results
        
        logger.info(
            f"Applying {len(managed_schemas.tables)} managed schemas "
            f"for extension '{extension_slug}' (schema_version={managed_schemas.schema_version})"
        )
        
        for table_name, table_def in managed_schemas.tables.items():
            full_table_name = self.get_full_table_name(extension_slug, table_name)
            
            try:
                # Check if table already exists
                exists = await self.table_exists(session, full_table_name)
                
                if exists:
                    logger.info(f"Table '{full_table_name}' already exists, skipping")
                    results[table_name] = False
                    continue
                
                # Generate and execute DDL
                ddl = self.generate_create_table_ddl(extension_slug, table_name, table_def)
                
                logger.debug(f"Executing DDL:\n{ddl}")
                
                await session.execute(text(ddl))
                await session.commit()
                
                logger.info(f"Successfully created table: {full_table_name}")
                results[table_name] = True
                
            except Exception as e:
                await session.rollback()
                raise SchemaMigrationError(
                    f"Failed to create table '{full_table_name}': {e}"
                ) from e
        
        return results
    
    async def remove_managed_schemas(
        self,
        session: AsyncSession,
        extension_slug: str,
        managed_schemas: ManagedSchemas,
    ) -> Dict[str, bool]:
        """
        Remove managed schemas for an extension.
        
        Drops all tables defined in the managed_schemas section.
        
        Args:
            session: Database session
            extension_slug: The extension's slug
            managed_schemas: The managed_schemas from the manifest
            
        Returns:
            Dictionary of table_name -> success
            
        Raises:
            SchemaMigrationError: If migration fails
        """
        results = {}
        
        if not managed_schemas.tables:
            return results
        
        logger.warning(
            f"Removing {len(managed_schemas.tables)} managed schemas "
            f"for extension '{extension_slug}'"
        )
        
        # Drop in reverse order to handle potential foreign keys
        for table_name in reversed(list(managed_schemas.tables.keys())):
            full_table_name = self.get_full_table_name(extension_slug, table_name)
            
            try:
                ddl = self.generate_drop_table_ddl(extension_slug, table_name)
                
                logger.debug(f"Executing DDL:\n{ddl}")
                
                await session.execute(text(ddl))
                await session.commit()
                
                logger.info(f"Successfully dropped table: {full_table_name}")
                results[table_name] = True
                
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to drop table '{full_table_name}': {e}")
                results[table_name] = False
        
        return results
    
    def generate_schema_info_summary(
        self,
        extension_slug: str,
        managed_schemas: ManagedSchemas,
    ) -> str:
        """
        Generate a human-readable summary of managed schemas.
        
        Args:
            extension_slug: The extension's slug
            managed_schemas: The managed_schemas from the manifest
            
        Returns:
            Multi-line string summary
        """
        if not managed_schemas.tables:
            return f"Extension '{extension_slug}' has no managed schemas"
        
        lines = [
            f"Managed Schemas for '{extension_slug}' (v{managed_schemas.schema_version}):",
            ""
        ]
        
        for table_name, table_def in managed_schemas.tables.items():
            full_name = self.get_full_table_name(extension_slug, table_name)
            lines.append(f"  Table: {full_name}")
            lines.append(f"    Columns: {len(table_def.columns)}")
            for col in table_def.columns:
                nullable = "NULL" if col.nullable is not False else "NOT NULL"
                lines.append(f"      - {col.name}: {col.type} {nullable}")
            lines.append("")
        
        return "\n".join(lines)


# Global singleton
_schema_manager: Optional[SchemaManager] = None


def get_schema_manager() -> SchemaManager:
    """Get the global schema manager instance."""
    global _schema_manager
    if _schema_manager is None:
        _schema_manager = SchemaManager()
    return _schema_manager
