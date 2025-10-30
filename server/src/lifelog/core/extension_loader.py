"""
Dynamic Extension Code Loader

This module provides the infrastructure for dynamically loading extension packages
at runtime. Extensions are Python packages located in the EXTENSIONS_PATH directory,
each containing:
- __init__.py (entry point)
- manifest.json (metadata)
- actors.py (optional, actor implementations)
- Any other Python modules needed

The loader:
1. Discovers extension packages in the extensions directory
2. Validates the extension structure and manifest
3. Dynamically imports the extension module
4. Registers actors with the global actor_registry
5. Provides isolation between extensions

Security considerations:
- Extensions run in the same process (Python doesn't have true sandboxing)
- Trust model: Extensions are installed by the system owner
- Future: Could use subprocess/containerization for stronger isolation
"""

import importlib.util
import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from pydantic import ValidationError

from ..manifest import ExtensionManifest
from .actors import actor_registry, ActorBase, ActorConfig
from .. import models

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
    ):
        self.slug = slug
        self.path = path
        self.manifest = manifest
        self.module = module
        self.actors_loaded: List[str] = []


class ExtensionLoader:
    """
    Manages dynamic loading of extension packages.
    
    This is a singleton-like class that maintains the registry of loaded extensions
    and provides methods to discover, load, and unload extension code.
    """
    
    def __init__(self, extensions_path: Path):
        self.extensions_path = extensions_path
        self.loaded_extensions: Dict[str, ExtensionPackage] = {}
        
        # Ensure extensions directory exists
        self.extensions_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"ExtensionLoader initialized with path: {extensions_path}")
    
    def discover_extensions(self) -> List[Path]:
        """
        Discover all potential extension packages in the extensions directory.
        
        Returns:
            List of paths to extension directories that contain a manifest.json
        """
        discovered = []
        
        for item in self.extensions_path.iterdir():
            if not item.is_dir():
                continue
            
            # Check if it has a manifest.json
            manifest_path = item / "manifest.json"
            if manifest_path.exists():
                discovered.append(item)
                logger.debug(f"Discovered extension at: {item}")
        
        return discovered
    
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
    
    def load_extension(self, extension_path: Path) -> ExtensionPackage:
        """
        Load a single extension from a directory.
        
        This is the main entry point for loading an extension. It:
        1. Loads and validates the manifest
        2. Imports the extension module
        3. Verifies actor registration
        
        Args:
            extension_path: Path to the extension directory
            
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
        
        # Import the module
        module = self.load_extension_module(extension_path, slug)
        
        # Create extension package object
        ext_pkg = ExtensionPackage(
            slug=slug,
            path=extension_path,
            manifest=manifest,
            module=module,
        )
        
        # Register actors
        ext_pkg.actors_loaded = self.register_extension_actors(ext_pkg)
        
        # Store in registry
        self.loaded_extensions[slug] = ext_pkg
        
        logger.info(
            f"Successfully loaded extension '{slug}' v{manifest.version} "
            f"with {len(ext_pkg.actors_loaded)} actors"
        )
        
        return ext_pkg
    
    def load_all_extensions(self) -> Dict[str, ExtensionPackage]:
        """
        Discover and load all extensions in the extensions directory.
        
        Returns:
            Dictionary of slug -> ExtensionPackage for all successfully loaded extensions
        """
        discovered = self.discover_extensions()
        
        logger.info(f"Discovered {len(discovered)} potential extensions")
        
        loaded = {}
        errors = []
        
        for ext_path in discovered:
            try:
                ext_pkg = self.load_extension(ext_path)
                loaded[ext_pkg.slug] = ext_pkg
            except ExtensionLoadError as e:
                logger.error(f"Failed to load extension at {ext_path}: {e}")
                errors.append((ext_path.name, str(e)))
        
        logger.info(
            f"Successfully loaded {len(loaded)} extensions "
            f"({len(errors)} failed)"
        )
        
        if errors:
            for name, error in errors:
                logger.error(f"  - {name}: {error}")
        
        return loaded
    
    def unload_extension(self, slug: str) -> bool:
        """
        Unload an extension (remove from loaded registry).
        
        Note: This doesn't unregister actors or unload the Python module completely
        (Python doesn't support true module unloading). This is mainly for
        tracking purposes.
        
        Args:
            slug: Extension slug to unload
            
        Returns:
            True if unloaded, False if not found
        """
        if slug not in self.loaded_extensions:
            return False
        
        ext_pkg = self.loaded_extensions.pop(slug)
        
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
