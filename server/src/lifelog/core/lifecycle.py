"""
Extension Lifecycle Management

Handles extension lifecycle hooks:
- on_install: Called when extension is first registered
- on_activate: Called when extension is enabled/loaded
- on_upgrade: Called when extension version changes
- on_deactivate: Called when extension is disabled
- on_uninstall: Called before extension is removed
"""

import logging
import inspect
from typing import Optional, Callable, Any
from sqlmodel.ext.asyncio.session import AsyncSession

logger = logging.getLogger(__name__)


class LifecycleError(Exception):
    """Raised when a lifecycle hook fails."""
    pass


class LifecycleManager:
    """
    Manages extension lifecycle hooks.
    
    Lifecycle hooks are optional async functions that extensions can define
    in their __init__.py module.
    """
    
    HOOK_NAMES = [
        "on_install",
        "on_activate", 
        "on_upgrade",
        "on_deactivate",
        "on_uninstall",
        "health_check"
    ]
    
    def __init__(self, extension_slug: str, module: Any):
        """
        Initialize lifecycle manager for an extension.
        
        Args:
            extension_slug: Extension slug
            module: The extension's Python module
        """
        self.extension_slug = extension_slug
        self.module = module
        self.hooks = self._discover_hooks()
    
    def _discover_hooks(self) -> dict[str, Callable]:
        """
        Discover lifecycle hooks defined in the extension module.
        
        Returns:
            Dict of hook_name -> callable
        """
        hooks = {}
        
        for hook_name in self.HOOK_NAMES:
            if hasattr(self.module, hook_name):
                hook_func = getattr(self.module, hook_name)
                
                # Validate it's callable
                if not callable(hook_func):
                    logger.warning(
                        f"Extension '{self.extension_slug}' has non-callable '{hook_name}'"
                    )
                    continue
                
                hooks[hook_name] = hook_func
                logger.info(f"Discovered lifecycle hook: {self.extension_slug}.{hook_name}")
        
        return hooks
    
    def has_hook(self, hook_name: str) -> bool:
        """Check if extension has a specific hook."""
        return hook_name in self.hooks
    
    async def run_hook(
        self,
        hook_name: str,
        session: Optional[AsyncSession] = None,
        **kwargs
    ) -> Any:
        """
        Run a lifecycle hook if it exists.
        
        Args:
            hook_name: Name of the hook to run
            session: Database session (passed to hooks that need it)
            **kwargs: Additional arguments to pass to the hook
            
        Returns:
            Hook return value (if any)
            
        Raises:
            LifecycleError: If hook execution fails
        """
        if hook_name not in self.hooks:
            logger.debug(f"No '{hook_name}' hook for '{self.extension_slug}'")
            return None
        
        hook_func = self.hooks[hook_name]
        
        # Track execution time and result
        import time
        start_time = time.time()
        success = False
        error_message = None
        result = None
        
        try:
            # Determine what arguments the hook accepts
            sig = inspect.signature(hook_func)
            call_kwargs = {}
            
            # Add session if hook accepts it
            if 'session' in sig.parameters and session is not None:
                call_kwargs['session'] = session
            
            # Add any other kwargs the hook accepts
            for param_name in sig.parameters:
                if param_name in kwargs:
                    call_kwargs[param_name] = kwargs[param_name]
            
            logger.info(f"Running lifecycle hook: {self.extension_slug}.{hook_name}")
            
            # Call the hook
            if inspect.iscoroutinefunction(hook_func):
                result = await hook_func(**call_kwargs)
            else:
                result = hook_func(**call_kwargs)
            
            success = True
            logger.info(f"✓ Completed lifecycle hook: {self.extension_slug}.{hook_name}")
            
        except Exception as e:
            error_message = str(e)
            error_msg = (
                f"Lifecycle hook '{hook_name}' failed for extension '{self.extension_slug}': {e}"
            )
            logger.error(error_msg, exc_info=True)
            raise LifecycleError(error_msg) from e
            
        finally:
            # Log the execution to database if session is available
            execution_time_ms = int((time.time() - start_time) * 1000)
            
            if session is not None:
                try:
                    await self._log_execution(
                        session,
                        hook_name,
                        success,
                        error_message,
                        execution_time_ms,
                        kwargs
                    )
                except Exception as log_error:
                    logger.warning(
                        f"Failed to log lifecycle hook execution: {log_error}"
                    )
        
        return result
    
    async def _log_execution(
        self,
        session: AsyncSession,
        hook_name: str,
        success: bool,
        error_message: Optional[str],
        execution_time_ms: int,
        context_kwargs: dict
    ) -> None:
        """
        Log lifecycle hook execution to database.
        
        Args:
            session: Database session
            hook_name: Hook name that was executed
            success: Whether execution succeeded
            error_message: Error message if failed
            execution_time_ms: Execution time in milliseconds
            context_kwargs: Additional context from kwargs
        """
        from .. import models
        from sqlmodel import select
        
        # Get extension ID
        stmt = select(models.Extension).where(models.Extension.slug == self.extension_slug)
        extension = (await session.exec(stmt)).one_or_none()
        
        if not extension:
            logger.warning(
                f"Cannot log lifecycle execution: extension '{self.extension_slug}' not found in DB"
            )
            return
        
        # Create log entry
        log_entry = models.ExtensionLifecycleLog(
            extension_id=extension.id,  # type: ignore[arg-type]
            hook_name=hook_name,
            success=success,
            error_message=error_message,
            execution_time_ms=execution_time_ms,
            context=context_kwargs if context_kwargs else None
        )
        
        session.add(log_entry)
        # Commit immediately so lifecycle logs persist even if caller doesn't commit
        await session.commit()
    
    async def on_install(self, session: AsyncSession) -> Any:
        """
        Run the on_install hook.
        
        Called once when extension is first registered in the database.
        Use for:
        - Seeding initial data
        - Creating custom indexes
        - One-time setup tasks
        
        Args:
            session: Database session
        """
        return await self.run_hook("on_install", session=session)
    
    async def on_activate(self, session: Optional[AsyncSession] = None) -> Any:
        """
        Run the on_activate hook.
        
        Called when extension is loaded/enabled.
        Use for:
        - Starting background tasks
        - Registering event listeners
        - Warming caches
        
        Args:
            session: Optional database session
        """
        return await self.run_hook("on_activate", session=session)
    
    async def on_upgrade(
        self,
        session: AsyncSession,
        old_version: str,
        new_version: str
    ) -> Any:
        """
        Run the on_upgrade hook.
        
        Called when extension version changes.
        Use for:
        - Data migrations
        - Schema updates
        - Config migrations
        
        Args:
            session: Database session
            old_version: Previous version string
            new_version: New version string
        """
        return await self.run_hook(
            "on_upgrade",
            session=session,
            old_version=old_version,
            new_version=new_version
        )
    
    async def on_deactivate(self, session: Optional[AsyncSession] = None) -> Any:
        """
        Run the on_deactivate hook.
        
        Called when extension is disabled.
        Use for:
        - Stopping background tasks
        - Cleaning up resources
        - Flushing caches
        
        Args:
            session: Optional database session
        """
        return await self.run_hook("on_deactivate", session=session)
    
    async def on_uninstall(self, session: AsyncSession) -> Any:
        """
        Run the on_uninstall hook.
        
        Called before extension is removed from database.
        Use for:
        - Final cleanup
        - Archiving data
        - Removing external resources
        
        Args:
            session: Database session
        """
        return await self.run_hook("on_uninstall", session=session)
    
    async def health_check(self, session: Optional[AsyncSession] = None) -> dict:
        """
        Run the health_check hook.
        
        Called to verify extension is functioning correctly.
        Extensions should return a dict with:
        - status: "healthy" | "degraded" | "unhealthy"
        - errors: List[str] (optional)
        - warnings: List[str] (optional)
        - details: dict (optional)
        
        If no health_check hook is defined, returns default healthy status.
        
        Args:
            session: Optional database session
            
        Returns:
            Health check result dict
        """
        if not self.has_hook("health_check"):
            # Default: extension is healthy if it's loaded
            return {
                "status": "healthy",
                "errors": [],
                "warnings": [],
                "details": {"message": "No health check hook defined"}
            }
        
        try:
            result = await self.run_hook("health_check", session=session)
            
            # Validate result format
            if not isinstance(result, dict):
                logger.warning(
                    f"health_check for '{self.extension_slug}' returned non-dict: {type(result)}"
                )
                return {
                    "status": "degraded",
                    "errors": [],
                    "warnings": ["Health check returned invalid format"],
                    "details": {"raw_result": str(result)}
                }
            
            # Ensure required fields
            if "status" not in result:
                result["status"] = "healthy"
            
            # Normalize status to valid values
            if result["status"] not in ["healthy", "degraded", "unhealthy"]:
                logger.warning(
                    f"health_check for '{self.extension_slug}' returned invalid status: {result['status']}"
                )
                result["status"] = "degraded"
                if "warnings" not in result:
                    result["warnings"] = []
                result["warnings"].append(f"Invalid status value: {result['status']}")
            
            # Ensure errors and warnings are lists
            result.setdefault("errors", [])
            result.setdefault("warnings", [])
            result.setdefault("details", {})
            
            return result
            
        except Exception as e:
            logger.error(
                f"health_check hook failed for '{self.extension_slug}': {e}",
                exc_info=True
            )
            return {
                "status": "unhealthy",
                "errors": [f"Health check failed: {str(e)}"],
                "warnings": [],
                "details": {"exception_type": type(e).__name__}
            }


def get_lifecycle_manager(extension_slug: str, module: Any) -> LifecycleManager:
    """
    Get a lifecycle manager for an extension.
    
    Args:
        extension_slug: Extension slug
        module: Extension module
        
    Returns:
        LifecycleManager instance
    """
    return LifecycleManager(extension_slug, module)
