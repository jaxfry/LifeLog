import logging

logger = logging.getLogger(__name__)


def load_all_actors():
    """
    This function imports all modules containing actor logic.
    Importing these modules triggers their @actor_registry.register decorators
    to run, populating the central registry.
    """
    # By importing here, we ensure the code runs when this function is called.
    from . import processors
    from . import enrichers
    try:
        from . import synthesis  # optional
    except ImportError:
        pass
    
    logger.info("All actor modules loaded and logic registered.")