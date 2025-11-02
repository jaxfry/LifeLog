"""
Dynamic Extension Code Loader

This module provides the infrastructure for dynamically loading extension packages
at runtime. Extensions can be:
- Python packages in directories (each containing __init__.py and manifest.json)
- Zipped extensions with .lifelog extension (zip files renamed to .lifelog)

The loader:
1. Discovers extension packages and .lifelog files in the extensions directory
2. Extracts .lifelog files to temporary directories
3. Validates the extension structure and manifest
4. Validates dependencies (core version, extensions, Python packages)
5. Dynamically imports the extension module
6. Registers actors with the global actor_registry
7. Auto-registers extensions in the database
8. Provides isolation between extensions

Security considerations:
- Extensions run in the same process (Python doesn't have true sandboxing)
- Trust model: Extensions are installed by the system owner
- Future: Could use subprocess/containerization for stronger isolation
"""

import importlib.util
import sys
import json
import logging
import zipfile
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any
from pydantic import ValidationError

from ..manifest import ExtensionManifest
from .actors import actor_registry, ActorBase, ActorConfig
from .dependency_validator import DependencyValidator, DependencyError
from .lifecycle import LifecycleManager
from .. import models
from .. import __version__ as LIFELOG_VERSION

logger = logging.getLogger(__name__)


class ExtensionLoadError(Exception):
    """Raised when an extension cannot be loaded."""
    pass


class ExtensionPackage:
    """Represents a loaded extension package."""
    
    def __init__(
        self,
        slug: str,
        path: Path,
        manifest: ExtensionManifest,
        module: Any,
        is_extracted: bool = False,
    ):
        self.slug = slug
        self.path = path
        self.manifest = manifest
        self.module = module
        self.actors_loaded: List[str] = []
        self.is_extracted = is_extracted  # True if extracted from .lifelog file
        self.lifecycle = LifecycleManager(slug, module)  # Lifecycle hook manager


class ExtensionLoader:
    """
    Manages dynamic loading of extension packages.
    
    This is a singleton-like class that maintains the registry of loaded extensions
    and provides methods to discover, load, and unload extension code.
    """
    
    def __init__(self, extensions_path: Path):
        self.extensions_path = extensions_path
        self.loaded_extensions: Dict[str, ExtensionPackage] = {}
        self.temp_dir = Path(tempfile.mkdtemp(prefix="lifelog_extensions_"))
        self.dependency_validator = DependencyValidator(LIFELOG_VERSION)
        
        # Ensure extensions directory exists
        self.extensions_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"ExtensionLoader initialized with path: {extensions_path}")
        logger.info(f"Core version: {LIFELOG_VERSION}")
        logger.info(f"Temporary extraction directory: {self.temp_dir}")
    
    def discover_extensions(self) -> List[Path]:
        """
        Discover all potential extension packages in the extensions directory.
        
        Looks for:
        - Directories containing manifest.json
        - .lifelog files (zipped extensions)
        
        Returns:
            List of paths to extension directories (including extracted .lifelog files)
        """
        discovered = []
        
        for item in self.extensions_path.iterdir():
            # Check for directory-based extensions
            if item.is_dir():
                manifest_path = item / "manifest.json"
                if manifest_path.exists():
                    discovered.append(item)
                    logger.debug(f"Discovered directory extension at: {item}")
            
            # Check for .lifelog zipped extensions
            elif item.is_file() and item.suffix == ".lifelog":
                try:
                    extracted_path = self._extract_lifelog_file(item)
                    discovered.append(extracted_path)
                    logger.debug(f"Discovered zipped extension at: {item}")
                except Exception as e:
                    logger.error(f"Failed to extract .lifelog file {item}: {e}")
        
        return discovered
    
    def _extract_lifelog_file(self, lifelog_path: Path) -> Path:
        """
        Extract a .lifelog file (renamed zip) to a temporary directory.
        
        Args:
            lifelog_path: Path to the .lifelog file
            
        Returns:
            Path to the extracted directory
            
        Raises:
            ExtensionLoadError: If extraction fails
        """
        # Create extraction directory based on filename
        extract_dir = self.temp_dir / lifelog_path.stem
        extract_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            with zipfile.ZipFile(lifelog_path, 'r') as zip_ref:
                # Validate it's a proper zip file
                if zip_ref.testzip() is not None:
                    raise ExtensionLoadError(f"Corrupted zip file: {lifelog_path}")
                
                # Extract all contents
                zip_ref.extractall(extract_dir)
                
                logger.info(f"Extracted {lifelog_path} to {extract_dir}")
                
                # Verify manifest exists after extraction
                if not (extract_dir / "manifest.json").exists():
                    raise ExtensionLoadError(
                        f"No manifest.json found in {lifelog_path} after extraction"
                    )
                
                return extract_dir
                
        except zipfile.BadZipFile as e:
            raise ExtensionLoadError(f"Invalid .lifelog file (not a valid zip): {e}")
        except Exception as e:
            raise ExtensionLoadError(f"Failed to extract {lifelog_path}: {e}")
    
    def load_manifest(self, extension_path: Path) -> ExtensionManifest:
        """
        Load and validate the manifest.json from an extension directory.
        
        Args:
            extension_path: Path to the extension directory
            
        Returns:
            Parsed and validated ExtensionManifest
            
        Raises:
            ExtensionLoadError: If manifest is invalid or missing
        """
        manifest_path = extension_path / "manifest.json"
        
        if not manifest_path.exists():
            raise ExtensionLoadError(f"No manifest.json found in {extension_path}")
        
        try:
            with open(manifest_path, 'r') as f:
                manifest_data = json.load(f)
            
            manifest = ExtensionManifest(**manifest_data)
            return manifest
            
        except json.JSONDecodeError as e:
            raise ExtensionLoadError(f"Invalid JSON in manifest: {e}")
        except ValidationError as e:
            raise ExtensionLoadError(f"Invalid manifest schema: {e}")
    
    def load_extension_module(self, extension_path: Path, slug: str) -> Any:
        """
        Dynamically import the extension's Python module.
        
        Args:
            extension_path: Path to the extension directory
            slug: Extension slug (used for module naming)
            
        Returns:
            The imported module object
            
        Raises:
            ExtensionLoadError: If module cannot be imported
        """
        init_path = extension_path / "__init__.py"
        
        if not init_path.exists():
            raise ExtensionLoadError(f"No __init__.py found in {extension_path}")
        
        # Create a unique module name to avoid collisions
        module_name = f"lifelog_extensions.{slug}"
        
        try:
            # Load the module spec
            spec = importlib.util.spec_from_file_location(module_name, init_path)
            if spec is None or spec.loader is None:
                raise ExtensionLoadError(f"Could not create module spec for {slug}")
            
            # Create the module
            module = importlib.util.module_from_spec(spec)
            
            # Add to sys.modules so imports within the extension work
            sys.modules[module_name] = module
            
            # Execute the module
            spec.loader.exec_module(module)
            
            logger.info(f"Successfully loaded extension module: {module_name}")
            return module
            
        except Exception as e:
            # Clean up sys.modules if load failed
            sys.modules.pop(module_name, None)
            raise ExtensionLoadError(f"Failed to load extension module {slug}: {e}")
    
    def register_extension_actors(
        self,
        extension_pkg: ExtensionPackage,
    ) -> List[str]:
        """
        Register actors from an extension with the global actor registry.
        
        The extension's __init__.py should use @actor_registry.register decorators
        to register its actors. This method verifies that the actors declared in
        the manifest have been registered.
        
        Args:
            extension_pkg: The loaded extension package
            
        Returns:
            List of actor slugs that were successfully registered
            
        Raises:
            ExtensionLoadError: If declared actors are not registered
        """
        registered = []
        
        if not extension_pkg.manifest.server_side:
            return registered
        
        # Check that all declared actors were registered
        for actor_decl in extension_pkg.manifest.server_side.actors:
            actor_slug = actor_decl.slug
            
            # Check if the actor was registered
            actor_config = actor_registry.get_actor_config(actor_slug)
            if actor_config is None:
                logger.warning(
                    f"Actor '{actor_slug}' declared in manifest but not registered "
                    f"by extension '{extension_pkg.slug}'. The extension's __init__.py "
                    f"should use @actor_registry.register() decorators."
                )
                continue
            
            # Verify the version matches
            if actor_config.version != actor_decl.version:
                logger.warning(
                    f"Actor '{actor_slug}' version mismatch: "
                    f"manifest says {actor_decl.version}, code says {actor_config.version}"
                )
            
            registered.append(actor_slug)
            logger.info(f"Verified actor registration: {actor_slug}")
        
        return registered
    
    async def load_extension(self, extension_path: Path) -> ExtensionPackage:
        """
        Load a single extension from a directory.
        
        This is the main entry point for loading an extension. It:
        1. Loads and validates the manifest
        2. Validates dependencies
        3. Imports the extension module
        4. Verifies actor registration
        5. Auto-registers in database
        
        Args:
            extension_path: Path to the extension directory (could be extracted from .lifelog)
            
        Returns:
            ExtensionPackage object
            
        Raises:
            ExtensionLoadError: If loading fails at any step
        """
        # Load manifest
        manifest = self.load_manifest(extension_path)
        slug = manifest.slug
        
        # Check if already loaded
        if slug in self.loaded_extensions:
            logger.warning(f"Extension '{slug}' is already loaded, skipping")
            return self.loaded_extensions[slug]
        
        # Validate dependencies
        self._validate_dependencies(manifest)
        
        # Import the module
        module = self.load_extension_module(extension_path, slug)
        
        # Determine if this was extracted from a .lifelog file
        is_extracted = self.temp_dir in extension_path.parents
        
        # Create extension package object
        ext_pkg = ExtensionPackage(
            slug=slug,
            path=extension_path,
            manifest=manifest,
            module=module,
            is_extracted=is_extracted,
        )
        
        # Register actors
        ext_pkg.actors_loaded = self.register_extension_actors(ext_pkg)

        # Auto-register in database and check if active
        is_active, is_upgrade, is_new_install = await self._auto_register_in_database(ext_pkg)

        if not is_active:
            # Extension is disabled, don't add to loaded registry
            logger.info(f"Skipping disabled extension: {slug}")
            return ext_pkg

        # Before storing, enforce external execution mode if configured
        try:
            from ..db import async_session
            async with async_session() as session:
                from sqlmodel import select
                db_ext_stmt = select(models.Extension).where(models.Extension.slug == slug)
                db_ext = (await session.exec(db_ext_stmt)).one_or_none()
                if db_ext and db_ext.config and db_ext.config.get("execution_mode") == "external":
                    logger.info(
                        f"Extension '{slug}' is configured for external execution. "
                        "Skipping in-process code registration."
                    )
                    # Ensure module isn't kept in sys.modules
                    module_name = f"lifelog_extensions.{slug}"
                    sys.modules.pop(module_name, None)
                    return ext_pkg
        except Exception as e:
            logger.warning(f"Failed to enforce external execution mode for '{slug}': {e}")

        # Store in registry (only if active and not external-only)
        self.loaded_extensions[slug] = ext_pkg

        # Update dependency validator with newly loaded extension
        self._update_installed_extensions()

        # Apply any pending migrations (for new installations)
        await self._apply_extension_migrations(ext_pkg)

        # Call lifecycle hooks for install/upgrade before activation
        try:
            from ..db import async_session
            async with async_session() as session:
                if is_new_install:
                    try:
                        await ext_pkg.lifecycle.on_install(session=session)
                        logger.info(f"✓ on_install completed for extension: {slug}")
                    except Exception as e:
                        logger.warning(f"on_install hook failed for '{slug}': {e}")
                elif is_upgrade:
                    # Fetch previous version from DB for context
                    from sqlmodel import select
                    from ..models import Extension as DbExtension
                    stmt = select(DbExtension).where(DbExtension.slug == slug)
                    db_ext = (await session.exec(stmt)).one_or_none()
                    old_version = db_ext.version if db_ext else "unknown"
                    try:
                        await ext_pkg.lifecycle.on_upgrade(
                            session=session,
                            old_version=old_version,
                            new_version=manifest.version
                        )
                        logger.info(f"✓ on_upgrade completed for extension: {slug}")
                    except Exception as e:
                        logger.warning(f"on_upgrade hook failed for '{slug}': {e}")
        except Exception as e:
            logger.debug(f"Lifecycle pre-activation hooks encountered an error: {e}")

        # Call on_activate lifecycle hook (with session for logging)
        try:
            from ..db import async_session
            async with async_session() as session:
                await ext_pkg.lifecycle.on_activate(session=session)
            logger.info(f"✓ Activated extension: {slug}")
        except Exception as e:
            logger.warning(f"on_activate hook failed for '{slug}': {e}")

        source_type = ".lifelog file" if is_extracted else "directory"
        logger.info(
            f"Successfully loaded extension '{slug}' v{manifest.version} "
            f"from {source_type} with {len(ext_pkg.actors_loaded)} actors"
        )

        # Mark prior errors for this extension as resolved
        try:
            from ..db import async_session
            from ..services import ExtensionErrorService
            async with async_session() as session:
                await ExtensionErrorService.resolve_errors_for_extension(session, slug)
        except Exception as e:
            logger.debug(f"Failed to mark prior errors resolved for '{slug}': {e}")

        return ext_pkg
    
    def _validate_dependencies(self, manifest: ExtensionManifest) -> None:
        """
        Validate extension dependencies.
        
        Args:
            manifest: Extension manifest to validate
            
        Raises:
            ExtensionLoadError: If dependencies are not satisfied
        """
        if not manifest.dependencies:
            return
        
        # Update validator with currently loaded extensions
        self._update_installed_extensions()
        
        # Validate all dependencies
        is_valid, errors = self.dependency_validator.validate_manifest(
            manifest,
            skip_python_packages=False  # Check Python packages
        )
        
        if not is_valid:
            error_msg = f"Dependency validation failed for '{manifest.slug}':\n"
            error_msg += "\n".join(f"  - {err}" for err in errors)
            
            # Log dependency tree for debugging
            dep_tree = self.dependency_validator.get_dependency_tree(manifest)
            logger.error(error_msg)
            logger.error(f"Dependency tree for '{manifest.slug}':")
            if dep_tree["core"]:
                logger.error(f"  Core: {', '.join(dep_tree['core'])}")
            if dep_tree["extensions"]:
                logger.error(f"  Extensions: {', '.join(dep_tree['extensions'])}")
            if dep_tree["python_packages"]:
                logger.error(f"  Python packages: {', '.join(dep_tree['python_packages'])}")
            
            raise ExtensionLoadError(error_msg)
        
        logger.info(f"✓ Dependencies validated for '{manifest.slug}'")
    
    def _update_installed_extensions(self) -> None:
        """Update dependency validator with currently loaded extensions."""
        installed = {
            slug: pkg.manifest.version
            for slug, pkg in self.loaded_extensions.items()
        }
        self.dependency_validator.set_installed_extensions(installed)
    
    async def _apply_extension_migrations(self, ext_pkg: ExtensionPackage) -> None:
        """
        Apply any pending migrations for an extension.
        
        Args:
            ext_pkg: The loaded extension package
        """
        from ..db import async_session
        from .migration_manager import get_migration_manager
        
        try:
            async with async_session() as session:
                # Get extension from database to get its ID
                from ..models import Extension
                from sqlmodel import select
                
                stmt = select(Extension).where(Extension.slug == ext_pkg.slug)
                result = await session.exec(stmt)
                extension = result.one_or_none()
                
                if not extension:
                    logger.warning(
                        f"Extension '{ext_pkg.slug}' not found in database, skipping migrations"
                    )
                    return
                
                # Apply pending migrations
                migration_manager = get_migration_manager()
                applied_migrations = await migration_manager.apply_pending_migrations(
                    session,
                    extension.id,  # type: ignore[arg-type]
                    ext_pkg.manifest.version,
                    ext_pkg.path
                )
                
                if applied_migrations:
                    logger.info(
                        f"✓ Applied {len(applied_migrations)} migration(s) for '{ext_pkg.slug}'"
                    )
                    
        except Exception as e:
            logger.error(
                f"Failed to apply migrations for '{ext_pkg.slug}': {e}",
                exc_info=True
            )
            # Don't fail the extension load, just log the error
    
    async def _auto_register_in_database(self, ext_pkg: ExtensionPackage) -> tuple[bool, bool, bool]:
        """
        Automatically register an extension in the database.
        
        This method is called during extension loading to ensure the extension
        metadata is persisted in the database without requiring a manual API call.
        
        Args:
            ext_pkg: The loaded extension package
            
        Returns:
            Tuple:
              - is_active: bool - whether extension is active and should be loaded
              - is_upgrade: bool - whether this load corresponds to a version upgrade
              - is_new_install: bool - whether this is the first time extension is registered
        """
        from ..db import async_session
        from ..services import ExtensionService
        
        try:
            async with async_session() as session:
                # Determine if extension already exists to infer new install vs update
                from sqlmodel import select
                from ..models import Extension as DbExtension
                pre_stmt = select(DbExtension).where(DbExtension.slug == ext_pkg.manifest.slug)
                pre_existing = (await session.exec(pre_stmt)).one_or_none()

                extension, is_upgrade = await ExtensionService.create_extension_from_manifest(
                    session,
                    ext_pkg.manifest,
                    update_if_exists=True
                )
                
                # Check if extension is active
                if not extension.is_active:
                    logger.info(
                        f"⊗ Extension '{ext_pkg.slug}' is disabled in database, skipping activation"
                    )
                    return False, is_upgrade, pre_existing is None
                
                if is_upgrade:
                    logger.info(
                        f"✓ Updated extension '{ext_pkg.slug}' in database: "
                        f"v{ext_pkg.manifest.version}"
                    )
                else:
                    logger.info(
                        f"✓ Registered new extension '{ext_pkg.slug}' in database: "
                        f"v{ext_pkg.manifest.version}"
                    )
                
                return True, is_upgrade, pre_existing is None
                
        except Exception as e:
            # Log the error but don't fail the extension load
            # The extension code can still work even if DB registration fails
            logger.error(
                f"Failed to auto-register extension '{ext_pkg.slug}' in database: {e}",
                exc_info=True
            )
            logger.warning(
                f"Extension '{ext_pkg.slug}' code is loaded but may not be visible in API"
            )
            # Assume active if we can't check the database
            return True, False, False
    
    async def load_all_extensions(self) -> Dict[str, ExtensionPackage]:
        """
        Discover and load all extensions in the extensions directory.
        
        Auto-registers extensions in the database during startup.
        Extensions are loaded in dependency order (dependencies first).
        
        Returns:
            Dictionary of slug -> ExtensionPackage for all successfully loaded extensions
        """
        discovered = self.discover_extensions()
        
        logger.info(f"Discovered {len(discovered)} potential extensions")
        
        # Load manifests for all discovered extensions
        manifests_by_path: Dict[Path, ExtensionManifest] = {}
        for ext_path in discovered:
            try:
                manifest = self.load_manifest(ext_path)
                manifests_by_path[ext_path] = manifest
            except Exception as e:
                logger.error(f"Failed to load manifest from {ext_path}: {e}")
                # Log error to database
                try:
                    from ..db import async_session
                    from ..services import ExtensionErrorService
                    # Best-effort slug from folder/file name
                    ext_slug_guess = ext_path.name
                    async with async_session() as session:
                        await ExtensionErrorService.log_error(
                            session,
                            extension_slug=ext_slug_guess,
                            error_type="manifest",
                            error_message=str(e),
                        )
                except Exception as log_e:
                    logger.warning(f"Could not persist manifest error for '{ext_path}': {log_e}")
        
        # Sort by dependencies (topological sort)
        ordered_paths = self._sort_by_dependencies(manifests_by_path)
        
        loaded = {}
        errors = []
        
        for ext_path in ordered_paths:
            try:
                ext_pkg = await self.load_extension(ext_path)
                # Only count as loaded if it's actually in the registry (not disabled)
                if ext_pkg.slug in self.loaded_extensions:
                    loaded[ext_pkg.slug] = ext_pkg
            except ExtensionLoadError as e:
                logger.error(f"Failed to load extension at {ext_path}: {e}")
                errors.append((ext_path.name, str(e)))
                # Persist error with known slug from manifest
                try:
                    from ..db import async_session
                    from ..services import ExtensionErrorService
                    manifest = manifests_by_path.get(ext_path)
                    ext_slug = manifest.slug if manifest else ext_path.name
                    async with async_session() as session:
                        await ExtensionErrorService.log_error(
                            session,
                            extension_slug=ext_slug,
                            error_type="import",
                            error_message=str(e),
                        )
                except Exception as log_e:
                    logger.warning(f"Could not persist load error for '{ext_path}': {log_e}")
        
        logger.info(
            f"Successfully loaded {len(loaded)} extensions "
            f"({len(errors)} failed)"
        )
        
        if errors:
            for name, error in errors:
                logger.error(f"  - {name}: {error}")
        
        return loaded
    
    def _sort_by_dependencies(
        self,
        manifests_by_path: Dict[Path, ExtensionManifest]
    ) -> List[Path]:
        """
        Sort extensions by dependency order using topological sort.
        
        Extensions with no dependencies are loaded first.
        Extensions that depend on others are loaded after their dependencies.
        
        Args:
            manifests_by_path: Mapping of paths to manifests
            
        Returns:
            List of paths in dependency order
        """
        # Build dependency graph
        graph: Dict[str, List[str]] = {}
        slug_to_path: Dict[str, Path] = {}
        
        for path, manifest in manifests_by_path.items():
            slug_to_path[manifest.slug] = path
            deps = []
            if manifest.dependencies and manifest.dependencies.extensions:
                deps = list(manifest.dependencies.extensions.keys())
            graph[manifest.slug] = deps
        
        # Topological sort (Kahn's algorithm)
        # Count incoming edges for each node
        in_degree = {slug: 0 for slug in graph}
        for deps in graph.values():
            for dep in deps:
                if dep in in_degree:
                    in_degree[dep] += 1
        
        # Queue of nodes with no incoming edges
        queue = [slug for slug, degree in in_degree.items() if degree == 0]
        sorted_slugs = []
        
        while queue:
            # Sort alphabetically for deterministic ordering
            queue.sort()
            slug = queue.pop(0)
            sorted_slugs.append(slug)
            
            # For each dependent of this slug
            for dependent_slug, deps in graph.items():
                if slug in deps:
                    in_degree[dependent_slug] -= 1
                    if in_degree[dependent_slug] == 0:
                        queue.append(dependent_slug)
        
        # Check for cycles
        if len(sorted_slugs) != len(graph):
            logger.warning("Circular dependency detected in extensions")
            # Add remaining slugs anyway (best effort)
            for slug in graph:
                if slug not in sorted_slugs:
                    sorted_slugs.append(slug)
        
        # Convert slugs back to paths
        ordered_paths = [slug_to_path[slug] for slug in sorted_slugs if slug in slug_to_path]
        
        logger.info(f"Extension load order: {', '.join(sorted_slugs)}")
        
        return ordered_paths
    
    async def unload_extension(self, slug: str, session: Optional[Any] = None) -> bool:
        """
        Unload an extension (remove from loaded registry).
        
        This method:
        1. Calls the on_deactivate lifecycle hook
        2. Removes extension from loaded registry
        3. Cleans up Python module imports
        
        Note: This doesn't unregister actors or unload the Python module completely
        (Python doesn't support true module unloading). Actors remain registered
        in actor_registry but the extension won't be in loaded_extensions.
        
        Args:
            slug: Extension slug to unload
            session: Optional database session for lifecycle hooks
            
        Returns:
            True if unloaded, False if not found
        """
        if slug not in self.loaded_extensions:
            logger.warning(f"Cannot unload extension '{slug}': not loaded")
            return False
        
        ext_pkg = self.loaded_extensions.get(slug)
        if not ext_pkg:
            return False
        
        # Call on_deactivate lifecycle hook
        try:
            if session:
                await ext_pkg.lifecycle.on_deactivate(session=session)
            else:
                # Create a temporary session if needed
                from ..db import async_session
                async with async_session() as temp_session:
                    await ext_pkg.lifecycle.on_deactivate(session=temp_session)
            logger.info(f"✓ Called on_deactivate for extension: {slug}")
        except Exception as e:
            logger.warning(f"on_deactivate hook failed for '{slug}': {e}")
            # Don't fail the unload if hook fails
        
        # Remove from loaded registry
        self.loaded_extensions.pop(slug)
        
        # Remove from sys.modules
        module_name = f"lifelog_extensions.{slug}"
        sys.modules.pop(module_name, None)
        
        logger.info(f"Unloaded extension: {slug}")
        return True
    
    def get_extension(self, slug: str) -> Optional[ExtensionPackage]:
        """Get a loaded extension by slug."""
        return self.loaded_extensions.get(slug)
    
    def list_loaded_extensions(self) -> List[str]:
        """Get list of all loaded extension slugs."""
        return list(self.loaded_extensions.keys())
    
    def cleanup(self) -> None:
        """
        Clean up temporary extraction directory.
        
        Should be called during application shutdown.
        """
        if self.temp_dir.exists():
            try:
                shutil.rmtree(self.temp_dir)
                logger.info(f"Cleaned up temporary directory: {self.temp_dir}")
            except Exception as e:
                logger.error(f"Failed to clean up temporary directory: {e}")


# Global singleton instance (initialized at app startup)
_extension_loader: Optional[ExtensionLoader] = None


def init_extension_loader(extensions_path: Path) -> ExtensionLoader:
    """
    Initialize the global extension loader.
    
    Should be called once at application startup.
    """
    global _extension_loader
    _extension_loader = ExtensionLoader(extensions_path)
    return _extension_loader


def get_extension_loader() -> ExtensionLoader:
    """
    Get the global extension loader instance.
    
    Raises:
        RuntimeError: If loader not initialized
    """
    if _extension_loader is None:
        raise RuntimeError(
            "ExtensionLoader not initialized. "
            "Call init_extension_loader() first."
        )
    return _extension_loader
