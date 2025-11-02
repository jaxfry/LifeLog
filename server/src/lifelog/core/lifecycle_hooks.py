"""
Extension Lifecycle Hooks

Defines the lifecycle hook interface and manages hook execution.

Extensions can implement these optional hooks:
- on_install: First-time installation
- on_activate: Extension is being activated
- on_upgrade: Version changed
- on_deactivate: Extension is being deactivated
- on_uninstall: Extension is being removed
"""

import logging
import inspect
from typing import Any, Optional, Callable, Dict
from sqlmodel.ext.asyncio.session import AsyncSession

logger = logging.getLogger(__name__)


class LifecycleHookError(Exception):
    """Raised when a lifecycle hook fails."""
    pass


class LifecycleHooks:
    """
    Manages extension lifecycle hooks.
    
    Hooks are optional async functions that extensions can define:
    
    ```python
    # In extension's __init__.py
    
    async def on_install(session: AsyncSession):
        '''Called once when extension is first registered in DB'''
        # Seed initial data, create custom indexes, etc.
        await session.execute(
            text("CREATE INDEX idx_custom ON my_table(field)")
        )
    
    async def on_activate():
        '''Called when extension is loaded/enabled'''
        # Start background tasks, warm caches, etc.
        pass
    
    async def on_upgrade(session: AsyncSession, old_version: str, new_version: str):
        '''Called when extension version changes'''
        # Data migrations
        if old_version == "1.0.0" and new_version == "2.0.0":
            await session.execute(
                text("ALTER TABLE my_table ADD COLUMN new_field TEXT")
            )
    
    async def on_deactivate():
        '''Called when extension is being disabled'''
        # Stop background tasks, flush buffers, etc.
        pass
    
    async def on_uninstall(session: AsyncSession):
        '''Called before extension is removed from DB'''
        # Cleanup (optional - tables auto-drop via CASCADE)
        pass
    ```
    """
    
    SUPPORTED_HOOKS = [
        "on_install",
        "on_activate",
        "on_upgrade",
        "on_deactivate",
        "on_uninstall",
    ]
    
    @staticmethod
    async def call_hook(
        module: Any,
        hook_name: str,
        **kwargs
    ) -> bool:
        """
        Call a lifecycle hook if it exists in the module.
        
        Args:
            module: Extension module
            hook_name: Name of the hook (e.g., "on_install")
            **kwargs: Arguments to pass to the hook
            
        Returns:
            True if hook was called, False if not found
            
        Raises:
            LifecycleHookError: If hook fails
        """
        if not hasattr(module, hook_name):
            logger.debug(f"Hook '{hook_name}' not defined in module")
            return False
        
        hook_func = getattr(module, hook_name)
        
        if not callable(hook_func):
            logger.warning(f"'{hook_name}' exists but is not callable")
            return False
        
        try:
            # Check if it's async
            if inspect.iscoroutinefunction(hook_func):
                await hook_func(**kwargs)
            else:
                # Call sync function
                hook_func(**kwargs)
            
            logger.info(f"✓ Successfully called hook '{hook_name}'")
            return True
            
        except Exception as e:
            error_msg = f"Hook '{hook_name}' failed: {e}"
            logger.error(error_msg, exc_info=True)
            raise LifecycleHookError(error_msg) from e
    
    @staticmethod
    async def on_install(
        module: Any,
        session: AsyncSession,
        slug: str
    ) -> None:
        """
        Call on_install hook.
        
        Args:
            module: Extension module
            session: Database session
            slug: Extension slug (for logging)
        """
        logger.info(f"Running on_install hook for '{slug}'...")
        try:
            called = await LifecycleHooks.call_hook(module, "on_install", session=session)
            if called:
                logger.info(f"✓ on_install completed for '{slug}'")
        except LifecycleHookError as e:
            logger.error(f"on_install failed for '{slug}': {e}")
            # Don't raise - log and continue
    
    @staticmethod
    async def on_activate(
        module: Any,
        slug: str
    ) -> None:
        """
        Call on_activate hook.
        
        Args:
            module: Extension module
            slug: Extension slug (for logging)
        """
        logger.info(f"Running on_activate hook for '{slug}'...")
        try:
            called = await LifecycleHooks.call_hook(module, "on_activate")
            if called:
                logger.info(f"✓ on_activate completed for '{slug}'")
        except LifecycleHookError as e:
            logger.error(f"on_activate failed for '{slug}': {e}")
            # Don't raise - log and continue
    
    @staticmethod
    async def on_upgrade(
        module: Any,
        session: AsyncSession,
        slug: str,
        old_version: str,
        new_version: str
    ) -> None:
        """
        Call on_upgrade hook.
        
        Args:
            module: Extension module
            session: Database session
            slug: Extension slug (for logging)
            old_version: Previous version
            new_version: New version
        """
        logger.info(
            f"Running on_upgrade hook for '{slug}' "
            f"({old_version} → {new_version})..."
        )
        try:
            called = await LifecycleHooks.call_hook(
                module,
                "on_upgrade",
                session=session,
                old_version=old_version,
                new_version=new_version
            )
            if called:
                logger.info(f"✓ on_upgrade completed for '{slug}'")
        except LifecycleHookError as e:
            logger.error(f"on_upgrade failed for '{slug}': {e}")
            # Don't raise - log and continue
    
    @staticmethod
    async def on_deactivate(
        module: Any,
        slug: str
    ) -> None:
        """
        Call on_deactivate hook.
        
        Args:
            module: Extension module
            slug: Extension slug (for logging)
        """
        logger.info(f"Running on_deactivate hook for '{slug}'...")
        try:
            called = await LifecycleHooks.call_hook(module, "on_deactivate")
            if called:
                logger.info(f"✓ on_deactivate completed for '{slug}'")
        except LifecycleHookError as e:
            logger.error(f"on_deactivate failed for '{slug}': {e}")
            # Don't raise - log and continue
    
    @staticmethod
    async def on_uninstall(
        module: Any,
        session: AsyncSession,
        slug: str
    ) -> None:
        """
        Call on_uninstall hook.
        
        Args:
            module: Extension module
            session: Database session
            slug: Extension slug (for logging)
        """
        logger.info(f"Running on_uninstall hook for '{slug}'...")
        try:
            called = await LifecycleHooks.call_hook(module, "on_uninstall", session=session)
            if called:
                logger.info(f"✓ on_uninstall completed for '{slug}'")
        except LifecycleHookError as e:
            logger.error(f"on_uninstall failed for '{slug}': {e}")
            # Don't raise - log and continue
    
    @staticmethod
    def get_available_hooks(module: Any) -> Dict[str, bool]:
        """
        Get list of hooks available in a module.
        
        Args:
            module: Extension module
            
        Returns:
            Dict of hook_name -> is_defined
        """
        return {
            hook: hasattr(module, hook) and callable(getattr(module, hook))
            for hook in LifecycleHooks.SUPPORTED_HOOKS
        }
