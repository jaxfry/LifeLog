"""
Extension Configuration Schema Management

Provides a JSON Schema-based configuration system for extensions.
Extensions can declare configuration schemas in their manifests, and
users can set/update configuration values via API.

Features:
- JSON Schema validation
- Type coercion
- Secret masking (for API keys, passwords)
- Default values
- Required field validation
"""

import logging
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, validator
import json
from jsonschema import validate as json_schema_validate, ValidationError as JsonSchemaValidationError

logger = logging.getLogger(__name__)


class ConfigFieldSchema(BaseModel):
    """
    Schema for a single configuration field.
    
    Follows JSON Schema conventions with extensions for LifeLog-specific features.
    """
    type: str = Field(..., description="Field type: string, integer, number, boolean, array, object")
    description: Optional[str] = Field(None, description="Human-readable description")
    default: Optional[Any] = Field(None, description="Default value if not set")
    required: bool = Field(False, description="Whether field is required")
    secret: bool = Field(False, description="Whether to mask value in responses (e.g., API keys)")
    
    # Type-specific constraints
    minimum: Optional[float] = Field(None, description="Minimum value for numbers")
    maximum: Optional[float] = Field(None, description="Maximum value for numbers")
    min_length: Optional[int] = Field(None, description="Minimum length for strings")
    max_length: Optional[int] = Field(None, description="Maximum length for strings")
    pattern: Optional[str] = Field(None, description="Regex pattern for strings")
    enum: Optional[List[Any]] = Field(None, description="Allowed values")
    
    # Array-specific
    items: Optional[Dict[str, Any]] = Field(None, description="Schema for array items")
    min_items: Optional[int] = Field(None, description="Minimum array length")
    max_items: Optional[int] = Field(None, description="Maximum array length")
    
    # Object-specific
    properties: Optional[Dict[str, Any]] = Field(None, description="Schema for object properties")


class ConfigurationSchema(BaseModel):
    """
    Complete configuration schema for an extension.
    
    This is stored in the extension's manifest.json under 'config_schema'.
    """
    type: str = Field("object", description="Root type (always 'object')")
    properties: Dict[str, ConfigFieldSchema] = Field(..., description="Configuration properties")
    required_fields: List[str] = Field(default_factory=list, description="List of required field names")
    
    def to_json_schema(self) -> Dict[str, Any]:
        """Convert to standard JSON Schema format."""
        schema = {
            "type": self.type,
            "properties": {},
            "required": self.required_fields
        }
        
        for field_name, field_schema in self.properties.items():
            field_dict = {
                "type": field_schema.type,
            }
            
            if field_schema.description:
                field_dict["description"] = field_schema.description
            if field_schema.default is not None:
                field_dict["default"] = field_schema.default
            if field_schema.minimum is not None:
                field_dict["minimum"] = field_schema.minimum
            if field_schema.maximum is not None:
                field_dict["maximum"] = field_schema.maximum
            if field_schema.min_length is not None:
                field_dict["minLength"] = field_schema.min_length
            if field_schema.max_length is not None:
                field_dict["maxLength"] = field_schema.max_length
            if field_schema.pattern is not None:
                field_dict["pattern"] = field_schema.pattern
            if field_schema.enum is not None:
                field_dict["enum"] = field_schema.enum
            if field_schema.items is not None:
                field_dict["items"] = field_schema.items
            if field_schema.min_items is not None:
                field_dict["minItems"] = field_schema.min_items
            if field_schema.max_items is not None:
                field_dict["maxItems"] = field_schema.max_items
            if field_schema.properties is not None:
                field_dict["properties"] = field_schema.properties
            
            schema["properties"][field_name] = field_dict
        
        return schema


class ConfigurationManager:
    """
    Manages extension configuration validation and access.
    """
    
    def __init__(self, schema: Optional[Dict[str, Any]] = None):
        """
        Initialize configuration manager.
        
        Args:
            schema: JSON Schema dict for configuration (optional)
        """
        self.schema = schema
        self._config: Dict[str, Any] = {}
    
    def set_schema(self, schema: Dict[str, Any]) -> None:
        """Set the configuration schema."""
        self.schema = schema
    
    def validate_config(self, config: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate configuration against schema.
        
        Args:
            config: Configuration dict to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self.schema:
            return True, None
        
        try:
            json_schema_validate(instance=config, schema=self.schema)
            return True, None
        except JsonSchemaValidationError as e:
            return False, str(e)
    
    def apply_defaults(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply default values from schema to config.
        
        Args:
            config: Partial configuration
            
        Returns:
            Configuration with defaults applied
        """
        if not self.schema or "properties" not in self.schema:
            return config
        
        result = config.copy()
        
        for field_name, field_schema in self.schema["properties"].items():
            if field_name not in result and "default" in field_schema:
                result[field_name] = field_schema["default"]
        
        return result
    
    def mask_secrets(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Mask secret fields in configuration for safe display.
        
        Args:
            config: Configuration dict
            
        Returns:
            Configuration with secrets masked as "***"
        """
        if not self.schema or "properties" not in self.schema:
            return config
        
        result = config.copy()
        
        # Check manifest schema structure for secret fields
        properties = self.schema.get("properties", {})
        
        for field_name, field_value in result.items():
            if field_name in properties:
                field_schema = properties[field_name]
                # Check if field is marked as secret
                if isinstance(field_schema, dict) and field_schema.get("secret", False):
                    result[field_name] = "***"
        
        return result
    
    def get_config(self, mask_secrets: bool = False) -> Dict[str, Any]:
        """
        Get current configuration.
        
        Args:
            mask_secrets: Whether to mask secret fields
            
        Returns:
            Configuration dict
        """
        config = self._config.copy()
        if mask_secrets:
            config = self.mask_secrets(config)
        return config
    
    def set_config(self, config: Dict[str, Any], validate: bool = True) -> None:
        """
        Set configuration.
        
        Args:
            config: New configuration
            validate: Whether to validate against schema
            
        Raises:
            ValueError: If validation fails
        """
        if validate:
            is_valid, error = self.validate_config(config)
            if not is_valid:
                raise ValueError(f"Configuration validation failed: {error}")
        
        # Apply defaults
        config_with_defaults = self.apply_defaults(config)
        
        self._config = config_with_defaults
    
    def update_config(self, updates: Dict[str, Any], validate: bool = True) -> None:
        """
        Update specific configuration fields.
        
        Args:
            updates: Fields to update
            validate: Whether to validate after update
            
        Raises:
            ValueError: If validation fails
        """
        new_config = self._config.copy()
        new_config.update(updates)
        
        self.set_config(new_config, validate=validate)
    
    def get_field(self, field_name: str, default: Any = None) -> Any:
        """
        Get a specific configuration field.
        
        Args:
            field_name: Field name
            default: Default value if field not set
            
        Returns:
            Field value or default
        """
        return self._config.get(field_name, default)
    
    def reset_to_defaults(self) -> None:
        """Reset configuration to schema defaults."""
        if not self.schema or "properties" not in self.schema:
            self._config = {}
            return
        
        defaults = {}
        for field_name, field_schema in self.schema["properties"].items():
            if "default" in field_schema:
                defaults[field_name] = field_schema["default"]
        
        self._config = defaults


def create_config_manager(schema: Optional[Dict[str, Any]] = None) -> ConfigurationManager:
    """
    Factory function to create a configuration manager.
    
    Args:
        schema: Optional JSON Schema for configuration
        
    Returns:
        ConfigurationManager instance
    """
    return ConfigurationManager(schema)
