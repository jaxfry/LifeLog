# central_server/processing_service/logic/event_aggregation.py
"""
Event aggregation module for LifeLog Data Processing Service.
This module is responsible for aggregating raw event data into a format
suitable for LLM processing.
"""

import logging
from typing import List

import polars as pl

from central_server.processing_service.logic.settings import Settings as ServiceSettingsType
from central_server.processing_service.models import ProcessingEventData

log = logging.getLogger(__name__)


class EventAggregator:
    """Aggregates and prepares events for LLM processing."""

    def __init__(self, settings: ServiceSettingsType):
        self.settings = settings

    def aggregate_events_from_data(self, events_data: List[ProcessingEventData]) -> pl.DataFrame:
        """
        Aggregates ProcessingEventData objects into a Polars DataFrame for the LLM.

        Args:
            events_data: A list of ProcessingEventData objects.

        Returns:
            A Polars DataFrame formatted for the LLM prompt.
        """
        if not events_data:
            return pl.DataFrame()

        # Ensure all dicts have the same keys and types
        all_keys = set()
        dict_events_raw = [event.model_dump() for event in events_data]
        for d in dict_events_raw:
            all_keys.update(d.keys())
        # Set default values for missing keys (None for non-str, "" for str fields)
        normalized_dicts = []
        for d in dict_events_raw:
            norm = {}
            for k in all_keys:
                v = d.get(k, None)
                # If any value is a string, default to "" if missing
                if v is None:
                    # Guess type by checking other dicts
                    for other in dict_events_raw:
                        if k in other and other[k] is not None:
                            v = "" if isinstance(other[k], str) else None
                            break
                    else:
                        v = None
                norm[k] = v
            normalized_dicts.append(norm)
        df = pl.from_dicts(normalized_dicts)

        if "start_time" not in df.columns or "end_time" not in df.columns:
            log.error("DataFrame from ProcessingEventData is missing 'start_time' or 'end_time'.")
            return pl.DataFrame()

        df_activities = df.filter(pl.col("app") != self.settings.AFK_APP_NAME)

        if df_activities.is_empty():
            log.info("No non-AFK activities in this batch of ProcessingEventData.")
            return pl.DataFrame()

        if self.settings.ENRICHMENT_MIN_DURATION_S > 0:
            df_activities = df_activities.filter(pl.col("duration_s") >= self.settings.ENRICHMENT_MIN_DURATION_S)

        if df_activities.is_empty():
            log.info("No activities remaining after duration filter from ProcessingEventData.")
            return pl.DataFrame()

        truncate_limit = self.settings.ENRICHMENT_PROMPT_TRUNCATE_LIMIT
        ellipsis_suffix = "…"

        df_for_prompt = df_activities.sort("start_time").with_columns([
            pl.col("start_time").dt.strftime("%H:%M:%S").alias("time_display"),
            pl.col("duration_s").round(0).cast(pl.Int32),
            pl.when(pl.col("title").fill_null("").str.len_chars() > truncate_limit)
              .then(pl.col("title").fill_null("").str.slice(0, truncate_limit) + pl.lit(ellipsis_suffix))
              .otherwise(pl.col("title").fill_null(""))
              .alias("title"),
            pl.when(pl.col("url").fill_null("").str.len_chars() > truncate_limit)
              .then(pl.col("url").fill_null("").str.slice(0, truncate_limit) + pl.lit(ellipsis_suffix))
              .otherwise(pl.col("url").fill_null(""))
              .alias("url"),
        ])
        log.info(f"Prepared {df_for_prompt.height} activity events for LLM prompt from ProcessingEventData.")
        return df_for_prompt