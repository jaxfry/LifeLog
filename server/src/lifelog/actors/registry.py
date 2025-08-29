# This file is DEPRECATED and will be removed in a future version.
# All actor registration should now be done using the class-based
# registry located in `lifelog.core.actors`.
#
# from ..core.actors import actor_registry, ActorConfig, ActorBase
#
# @actor_registry.register(ActorConfig(...))
# class MyActor(ActorBase):
#     async def run(self, data):
#         ...

from ..core.actors import actor_registry

# For backwards compatibility, we can alias the new registry's
# decorator if needed, but it's better to update the call sites.
register_actor = actor_registry.register