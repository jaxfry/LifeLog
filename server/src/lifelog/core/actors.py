"""
Core Actor System for LifeLog

This module defines the foundational components for creating and managing actors,
which are the primary units of server-side logic in the LifeLog system. It moves
beyond a simple function registry to a class-based approach, allowing for more
structured, extensible, and maintainable actor implementations.

Key Components:
- ActorConfig: A Pydantic model for declaratively defining an actor's metadata,
  including its slug, type, and version. This aligns with the manifest-driven
  approach described in the system architecture.
- ActorBase: An abstract base class that all actors must inherit from. It
  provides a common interface and enforces the implementation of a `run` method,
  ensuring consistency across all actor types.
- ActorLogicRegistry: A sophisticated registry that stores and manages actor
  classes, mapping their slugs to the corresponding class definition. This
  replaces the previous function-based registry.

This structured approach provides better type safety, encourages separation of
concerns, and makes the actor system more aligned with the principles of a
modular, extension-first platform.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Type
import logging
from pydantic import BaseModel, Field
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from .. import models

logger = logging.getLogger(__name__)


class ActorConfig(BaseModel):
    """Declarative configuration for a server-side actor."""

    slug: str = Field(..., description="The unique identifier for the actor.")
    actor_type: models.ActorType = Field(
        ..., description="The functional type of the actor."
    )
    version: str = Field(
        ..., description="The semantic version of the actor's logic."
    )


class ActorBase(ABC):
    """Abstract base class for all server-side actor logic."""

    @abstractmethod
    async def run(self, data: Any) -> Any:
        """
        The main execution method for the actor.

        This method contains the core logic of the actor and must be implemented
        by all subclasses. It is designed to be asynchronous to support I/O-bound
        operations without blocking the server.

        Args:
            data: The input data for the actor to process. The shape of this
                  data will vary depending on the actor's type and purpose.

        Returns:
            The result of the actor's processing. The shape of the return
            value will also vary.
        """
        pass


class ActorLogicRegistry:
    """A registry for managing and discovering actor logic classes."""

    def __init__(self):
        self._registry: Dict[str, Type[ActorBase]] = {}
        self._configs: Dict[str, ActorConfig] = {}

    def register(self, config: ActorConfig):
        """
        A class decorator to register an actor with the system.

        This decorator associates an actor's declarative configuration with its
        logic class, making it discoverable by the core application.

        Args:
            config: An `ActorConfig` instance describing the actor.

        Returns:
            A decorator function that registers the class.
        """

        def decorator(cls: Type[ActorBase]):
            if config.slug in self._registry:
                # This is a developer error, so a simple warning is sufficient
                # for now. In a more robust system, this might raise an error
                # at startup.
                logger.warning(
                    "Actor with slug '%s' is already registered. Overwriting.",
                    config.slug
                )
            self._registry[config.slug] = cls
            self._configs[config.slug] = config
            logger.info("Registered actor '%s' version %s", config.slug, config.version)
            return cls

        return decorator

    def get_actor(self, slug: str) -> ActorBase | None:
        """
        Instantiates and returns an actor logic class.

        Args:
            slug: The slug of the actor to instantiate.

        Returns:
            An instance of the actor's class if found, otherwise None.
        """
        actor_class = self._registry.get(slug)
        if actor_class:
            instance = actor_class()
            # Attach config to the instance for easy access
            setattr(instance, "config", self._configs[slug])
            return instance
        return None

    async def get_actor_model(
        self, session: AsyncSession, slug: str
    ) -> models.Actor | None:
        """
        Retrieves the database model for a given actor slug.

        Args:
            session: The database session to use for the query.
            slug: The slug of the actor to retrieve.

        Returns:
            The SQLModel `Actor` instance if found, otherwise None.
        """
        stmt = select(models.Actor).where(models.Actor.slug == slug)
        result = await session.exec(stmt)
        return result.one_or_none()

    def get_actor_class(self, slug: str) -> Type[ActorBase] | None:
        """
        Retrieves the class for a given actor slug.

        Args:
            slug: The slug of the actor to retrieve.

        Returns:
            The actor class if found, otherwise None.
        """
        return self._registry.get(slug)

    def get_actor_config(self, slug: str) -> ActorConfig | None:
        """
        Retrieves the configuration for a given actor slug.

        Args:
            slug: The slug of the actor to retrieve.

        Returns:
            The ActorConfig instance if found, otherwise None.
        """
        return self._configs.get(slug)

    def get_all_configs(self) -> list[ActorConfig]:
        """
        Returns a list of all registered actor configurations.

        This is useful for tasks like seeding the database with all known
        actors at application startup.

        Returns:
            A list of `ActorConfig` objects.
        """
        return list(self._configs.values())


# Create a global instance of the registry for the application to use.
# This follows the singleton pattern, ensuring that all parts of the app
# share the same actor registry.
actor_registry = ActorLogicRegistry()