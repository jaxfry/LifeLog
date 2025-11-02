"""
Extension Dependency Validator

Validates extension dependencies including:
- Core version requirements
- Extension dependencies
- Python package availability

Follows semantic versioning (semver) conventions.
"""

import re
import logging
import importlib.metadata
from typing import Dict, List, Optional, Tuple
from packaging import version as pkg_version
from packaging.specifiers import SpecifierSet, InvalidSpecifier

from ..manifest import DependencyRequirements, ExtensionManifest

logger = logging.getLogger(__name__)


class DependencyError(Exception):
    """Raised when a dependency requirement cannot be satisfied."""
    pass


class DependencyValidator:
    """
    Validates extension dependencies.
    
    Supports semantic versioning ranges like:
    - ">=1.0.0" - Greater than or equal to
    - "^1.2.0" - Compatible with (>= 1.2.0, < 2.0.0)
    - "~1.2.0" - Approximately (>= 1.2.0, < 1.3.0)
    - "1.2.0" - Exact version
    - ">=1.0.0,<2.0.0" - Multiple constraints
    """
    
    def __init__(self, core_version: str):
        """
        Initialize validator with the current core version.
        
        Args:
            core_version: Current LifeLog core version (e.g., "1.0.0")
        """
        self.core_version = core_version
        self.installed_extensions: Dict[str, str] = {}
        
    def set_installed_extensions(self, extensions: Dict[str, str]) -> None:
        """
        Set the currently installed extensions.
        
        Args:
            extensions: Dict of {slug: version}
        """
        self.installed_extensions = extensions
    
    def validate_manifest(
        self,
        manifest: ExtensionManifest,
        skip_python_packages: bool = False
    ) -> Tuple[bool, List[str]]:
        """
        Validate all dependencies in a manifest.
        
        Args:
            manifest: Extension manifest to validate
            skip_python_packages: If True, skip Python package validation
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        if not manifest.dependencies:
            return True, []
        
        # Validate core version
        if manifest.dependencies.core:
            try:
                self.validate_core_version(manifest.dependencies.core)
            except DependencyError as e:
                errors.append(str(e))
        
        # Validate extension dependencies
        for ext_slug, version_req in manifest.dependencies.extensions.items():
            try:
                self.validate_extension_dependency(ext_slug, version_req)
            except DependencyError as e:
                errors.append(str(e))
        
        # Validate Python packages
        if not skip_python_packages and manifest.dependencies.python_packages:
            for package_req in manifest.dependencies.python_packages:
                try:
                    self.validate_python_package(package_req)
                except DependencyError as e:
                    errors.append(str(e))
        
        return len(errors) == 0, errors
    
    def validate_core_version(self, requirement: str) -> None:
        """
        Validate core version requirement.
        
        Args:
            requirement: Version requirement string (e.g., ">=1.0.0")
            
        Raises:
            DependencyError: If core version doesn't satisfy requirement
        """
        try:
            # Convert caret (^) and tilde (~) to standard specifiers
            specifier = self._convert_to_specifier(requirement)
            
            if not specifier.contains(self.core_version):
                raise DependencyError(
                    f"Core version requirement not met: "
                    f"requires {requirement}, but running {self.core_version}"
                )
        except InvalidSpecifier as e:
            raise DependencyError(f"Invalid core version specifier '{requirement}': {e}")
    
    def validate_extension_dependency(
        self,
        ext_slug: str,
        version_requirement: str
    ) -> None:
        """
        Validate that a required extension is installed with compatible version.
        
        Args:
            ext_slug: Extension slug to check
            version_requirement: Version requirement (e.g., "^1.0.0")
            
        Raises:
            DependencyError: If extension not installed or version incompatible
        """
        if ext_slug not in self.installed_extensions:
            raise DependencyError(
                f"Required extension '{ext_slug}' is not installed"
            )
        
        installed_version = self.installed_extensions[ext_slug]
        
        try:
            specifier = self._convert_to_specifier(version_requirement)
            
            if not specifier.contains(installed_version):
                raise DependencyError(
                    f"Extension '{ext_slug}' version mismatch: "
                    f"requires {version_requirement}, but installed version is {installed_version}"
                )
        except InvalidSpecifier as e:
            raise DependencyError(
                f"Invalid version specifier for '{ext_slug}': {version_requirement} ({e})"
            )
    
    def validate_python_package(self, package_requirement: str) -> None:
        """
        Validate that a Python package is installed.
        
        Args:
            package_requirement: Package requirement (e.g., "requests>=2.28.0")
            
        Raises:
            DependencyError: If package not installed or version incompatible
        """
        # Parse package name and version requirement
        # Format: "package-name>=1.0.0" or just "package-name"
        match = re.match(r'^([a-zA-Z0-9\-_\.]+)(.*)$', package_requirement)
        if not match:
            raise DependencyError(f"Invalid package requirement format: {package_requirement}")
        
        package_name = match.group(1)
        version_spec = match.group(2).strip() if match.group(2) else None
        
        try:
            installed_version = importlib.metadata.version(package_name)
            
            # If version specified, check it
            if version_spec:
                specifier = SpecifierSet(version_spec)
                if not specifier.contains(installed_version):
                    raise DependencyError(
                        f"Python package '{package_name}' version mismatch: "
                        f"requires {package_requirement}, but installed version is {installed_version}"
                    )
        except importlib.metadata.PackageNotFoundError:
            raise DependencyError(
                f"Required Python package '{package_name}' is not installed. "
                f"Install with: pip install {package_requirement}"
            )
    
    def _convert_to_specifier(self, requirement: str) -> SpecifierSet:
        """
        Convert semver-style requirements to PEP 440 specifiers.
        
        Handles:
        - "^1.2.3" -> ">=1.2.3,<2.0.0"
        - "~1.2.3" -> ">=1.2.3,<1.3.0"
        - Standard PEP 440 specifiers are passed through
        
        Args:
            requirement: Version requirement string
            
        Returns:
            SpecifierSet object
        """
        # Handle caret (^) - compatible with
        if requirement.startswith('^'):
            version_str = requirement[1:]
            v = pkg_version.Version(version_str)
            
            # ^1.2.3 means >=1.2.3,<2.0.0
            # ^0.2.3 means >=0.2.3,<0.3.0 (0.x is special)
            if v.major == 0:
                next_version = f"{v.major}.{v.minor + 1}.0"
            else:
                next_version = f"{v.major + 1}.0.0"
            
            return SpecifierSet(f">={version_str},<{next_version}")
        
        # Handle tilde (~) - approximately
        elif requirement.startswith('~'):
            version_str = requirement[1:]
            v = pkg_version.Version(version_str)
            
            # ~1.2.3 means >=1.2.3,<1.3.0
            next_version = f"{v.major}.{v.minor + 1}.0"
            
            return SpecifierSet(f">={version_str},<{next_version}")
        
        # Standard specifier
        else:
            return SpecifierSet(requirement)
    
    def get_dependency_tree(
        self,
        manifest: ExtensionManifest
    ) -> Dict[str, List[str]]:
        """
        Get the dependency tree for an extension.
        
        Returns:
            Dict mapping dependency type to list of requirements
        """
        tree = {
            "core": [],
            "extensions": [],
            "python_packages": []
        }
        
        if not manifest.dependencies:
            return tree
        
        if manifest.dependencies.core:
            tree["core"].append(manifest.dependencies.core)
        
        for slug, version_req in manifest.dependencies.extensions.items():
            tree["extensions"].append(f"{slug} {version_req}")
        
        tree["python_packages"] = manifest.dependencies.python_packages.copy()
        
        return tree


def validate_extension_dependencies(
    manifest: ExtensionManifest,
    core_version: str,
    installed_extensions: Dict[str, str],
    skip_python_packages: bool = False
) -> Tuple[bool, List[str]]:
    """
    Convenience function to validate extension dependencies.
    
    Args:
        manifest: Extension manifest to validate
        core_version: Current core version
        installed_extensions: Dict of installed extensions {slug: version}
        skip_python_packages: If True, skip Python package validation
        
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    validator = DependencyValidator(core_version)
    validator.set_installed_extensions(installed_extensions)
    return validator.validate_manifest(manifest, skip_python_packages)
