import logging
from .db import get_db_connection

log = logging.getLogger(__name__)

def run_transactional_job(job_fn, *args, **kwargs):
    """Creates a dedicated connection and runs the job in a transaction."""
    con = None
    job_name = job_fn.__name__
    try:
        con = get_db_connection()
        con.begin()
        log.info(f"JOB_START: {job_name}")
        job_fn(con, *args, **kwargs)
        con.commit()
        log.info(f"JOB_SUCCESS: {job_name}")
    except Exception as e:
        log.error(f"JOB_FAILURE: {job_name}", exc_info=True)
        if con:
            con.rollback()
        # The exception is allowed to propagate up to the main daemon loop
    finally:
        if con:
            con.close()