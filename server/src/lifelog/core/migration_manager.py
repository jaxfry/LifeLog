"""
Extension Migration Manager

Handles database schema migrations for extensions.
Extensions can include SQL migration files in a `migrations/` directory.
Migrations are applied in order and tracked in the ExtensionMigration table.

Migration file naming convention:
- migrations/001_initial_schema.sql
- migrations/002_add_columns.sql
- etc.

Migration files should be idempotent SQL scripts that:
- Create tables, indexes, etc.
- Add/modify columns
- Migrate data when needed

The migration manager:
1. Discovers migration files in extension directories
2. Checks which migrations have been applied
3. Applies pending migrations in order
4. Records applied migrations with checksums
5. Validates migration integrity
"""

import logging
import hashlib
from pathlib import Path
from typing import List, Optional, Tuple
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from sqlalchemy import text

from .. import models

logger = logging.getLogger(__name__)


class MigrationError(Exception):
    """Raised when a migration fails."""
    pass


class MigrationManager:
    """
    Manages database migrations for extensions.
    
    Each extension can have a `migrations/` directory containing SQL files.
    Migration files are named with a numeric prefix for ordering:
    - 001_description.sql
    - 002_description.sql
    etc.
    """
    
    MIGRATIONS_DIR = "migrations"
    
    def __init__(self):
        """Initialize migration manager."""
        pass
    
    def discover_migrations(self, extension_path: Path) -> List[Tuple[str, Path]]:
        """
        Discover migration files in an extension directory.
        
        Args:
            extension_path: Path to extension directory
            
        Returns:
            List of (migration_name, migration_path) tuples, sorted by name
        """
        migrations_dir = extension_path / self.MIGRATIONS_DIR
        
        if not migrations_dir.exists() or not migrations_dir.is_dir():
            return []
        
        migrations = []
        for file_path in migrations_dir.glob("*.sql"):
            migration_name = file_path.name
            migrations.append((migration_name, file_path))
        
        # Sort by filename (assumes numeric prefix like 001_, 002_, etc.)
        migrations.sort(key=lambda x: x[0])
        
        logger.debug(f"Discovered {len(migrations)} migrations in {extension_path}")
        return migrations
    
    async def get_applied_migrations(
        self,
        session: AsyncSession,
        extension_id: int
    ) -> List[models.ExtensionMigration]:
        """
        Get list of migrations already applied for an extension.
        
        Args:
            session: Database session
            extension_id: Extension ID
            
        Returns:
            List of ExtensionMigration records
        """
        stmt = (
            select(models.ExtensionMigration)
            .where(models.ExtensionMigration.extension_id == extension_id)
            .order_by(models.ExtensionMigration.applied_at)  # type: ignore[attr-defined]
        )
        result = await session.exec(stmt)
        return list(result.all())
    
    def calculate_checksum(self, file_path: Path) -> str:
        """
        Calculate SHA256 checksum of a migration file.
        
        Args:
            file_path: Path to migration file
            
        Returns:
            Hex digest of SHA256 hash
        """
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    async def apply_migration(
        self,
        session: AsyncSession,
        extension_id: int,
        extension_version: str,
        migration_name: str,
        migration_path: Path,
        from_version: Optional[str] = None
    ) -> models.ExtensionMigration:
        """
        Apply a single migration file.
        
        Args:
            session: Database session
            extension_id: Extension ID
            extension_version: Current extension version
            migration_name: Name of the migration file
            migration_path: Path to the migration file
            from_version: Previous extension version (if upgrade)
            
        Returns:
            ExtensionMigration record
            
        Raises:
            MigrationError: If migration fails
        """
        logger.info(f"Applying migration '{migration_name}' for extension ID {extension_id}")
        
        # Read migration SQL
        try:
            with open(migration_path, 'r') as f:
                sql_content = f.read()
        except Exception as e:
            raise MigrationError(f"Failed to read migration file '{migration_name}': {e}")
        
        # Calculate checksum
        checksum = self.calculate_checksum(migration_path)
        
        # Execute the migration SQL
        try:
            # Split into statements (basic split on semicolon)
            # Note: This is simple and won't handle all SQL edge cases
            # For production, consider using a proper SQL parser
            statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]
            
            # Use a single async connection for all statements
            conn = await session.connection()
            for stmt in statements:
                await conn.execute(text(stmt))  # type: ignore[union-attr]
            
            await session.commit()
            
        except Exception as e:
            await session.rollback()
            raise MigrationError(
                f"Failed to execute migration '{migration_name}': {e}"
            ) from e
        
        # Record the migration
        from datetime import timezone, datetime
        migration_record = models.ExtensionMigration(
            extension_id=extension_id,
            migration_name=migration_name,
            applied_at=datetime.now(timezone.utc),
            from_version=from_version,
            to_version=extension_version,
            checksum=checksum
        )
        
        session.add(migration_record)
        await session.commit()
        await session.refresh(migration_record)
        
        logger.info(
            f"✓ Applied migration '{migration_name}' for extension ID {extension_id}"
        )
        
        return migration_record
    
    async def apply_pending_migrations(
        self,
        session: AsyncSession,
        extension_id: int,
        extension_version: str,
        extension_path: Path,
        from_version: Optional[str] = None
    ) -> List[models.ExtensionMigration]:
        """
        Apply all pending migrations for an extension.
        
        Args:
            session: Database session
            extension_id: Extension ID
            extension_version: Current extension version
            extension_path: Path to extension directory
            from_version: Previous extension version (if upgrade)
            
        Returns:
            List of applied ExtensionMigration records
        """
        # Discover available migrations
        available_migrations = self.discover_migrations(extension_path)
        
        if not available_migrations:
            logger.debug(f"No migrations found for extension ID {extension_id}")
            return []
        
        # Get already applied migrations
        applied_migrations = await self.get_applied_migrations(session, extension_id)
        applied_names = {m.migration_name for m in applied_migrations}
        
        # Find pending migrations
        pending = [
            (name, path) for name, path in available_migrations
            if name not in applied_names
        ]
        
        if not pending:
            logger.info(f"No pending migrations for extension ID {extension_id}")
            return []
        
        logger.info(
            f"Applying {len(pending)} pending migration(s) for extension ID {extension_id}"
        )
        
        # Apply migrations in order
        applied = []
        for migration_name, migration_path in pending:
            try:
                migration_record = await self.apply_migration(
                    session,
                    extension_id,
                    extension_version,
                    migration_name,
                    migration_path,
                    from_version
                )
                applied.append(migration_record)
            except MigrationError as e:
                logger.error(
                    f"Migration '{migration_name}' failed, stopping migration process: {e}"
                )
                # Don't continue applying migrations after a failure
                raise
        
        return applied
    
    async def verify_migration_integrity(
        self,
        session: AsyncSession,
        extension_id: int,
        extension_path: Path
    ) -> List[Tuple[str, bool, Optional[str]]]:
        """
        Verify that applied migrations match their recorded checksums.
        
        Args:
            session: Database session
            extension_id: Extension ID
            extension_path: Path to extension directory
            
        Returns:
            List of (migration_name, is_valid, error_message) tuples
        """
        applied_migrations = await self.get_applied_migrations(session, extension_id)
        available_migrations = dict(self.discover_migrations(extension_path))
        
        results = []
        
        for migration_record in applied_migrations:
            migration_name = migration_record.migration_name
            
            if migration_name not in available_migrations:
                # Migration was applied but file is missing
                results.append((
                    migration_name,
                    False,
                    "Migration file not found"
                ))
                continue
            
            # Check checksum
            migration_path = available_migrations[migration_name]
            current_checksum = self.calculate_checksum(migration_path)
            
            if current_checksum != migration_record.checksum:
                results.append((
                    migration_name,
                    False,
                    f"Checksum mismatch (expected: {migration_record.checksum}, got: {current_checksum})"
                ))
            else:
                results.append((migration_name, True, None))
        
        return results


# Global singleton instance
_migration_manager: Optional[MigrationManager] = None


def get_migration_manager() -> MigrationManager:
    """
    Get the global migration manager instance.
    
    Creates a new instance if it doesn't exist.
    """
    global _migration_manager
    if _migration_manager is None:
        _migration_manager = MigrationManager()
    return _migration_manager
