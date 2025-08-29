def load_all_actors():
    """
    This function imports all modules containing actor logic.
    The act of importing them will cause their @register_actor decorators
    to run, populating the central registry.
    """
    # By importing here, we ensure the code runs when this function is called.
    from . import processors
    
    print("All actor modules loaded and logic registered.")