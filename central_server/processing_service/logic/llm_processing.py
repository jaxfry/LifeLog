# central_server/processing_service/logic/llm_processing.py
"""
LLM processing module for LifeLog Data Processing Service.
This module contains the classes responsible for interacting with the 
Google Gemini LLM, including caching responses.
"""

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone, timedelta, date
from typing import List, Optional

import polars as pl
from google import genai
from google.genai import types as genai_types

from central_server.processing_service.logic import prompts
from central_server.processing_service.logic.settings import Settings as ServiceSettingsType
from central_server.processing_service.models import TimelineEntry

log = logging.getLogger(__name__)


class LLMResponseCache:
    """Manages caching of LLM responses."""

    def __init__(self, settings: ServiceSettingsType):
        self.settings = settings
        self.cache_enabled = settings.ENABLE_LLM_CACHE
        self.cache_dir = settings.CACHE_DIR

        if self.cache_enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            log.info(f"LLM cache enabled, using directory: {self.cache_dir}")
        else:
            log.info("LLM cache disabled")

    def _generate_cache_key(self, events_df_chunk: pl.DataFrame, local_day: date, project_names: List[str]) -> str:
        """
        Generates a unique cache key for a given chunk of events.

        Args:
            events_df_chunk: The DataFrame of events.
            local_day: The local date of the events.
            project_names: A list of known project names.

        Returns:
            A unique string to be used as a cache key.
        """
        if events_df_chunk.is_empty():
            return f"empty_{local_day.isoformat()}_ps"

        cols_for_hash = ["time_display", "duration_s", "app", "title", "url"]
        present_cols = [col for col in cols_for_hash if col in events_df_chunk.columns]

        if not present_cols:
            data_str = ""
        else:
            data_str = (
                events_df_chunk
                .select(present_cols)
                .fill_null("")
                .sort(by=present_cols[0] if present_cols else "time_display", descending=False)
                .to_pandas()
                .to_string()
            )
        data_hash = hashlib.md5(data_str.encode()).hexdigest()
        project_hash = hashlib.md5(" ".join(sorted(project_names)).encode()).hexdigest()
        return f"{local_day.isoformat()}_{data_hash}_{project_hash}_ps"

    def get_cached_response(self, cache_key: str) -> Optional[List[TimelineEntry]]:
        """
        Retrieves a cached LLM response.

        Args:
            cache_key: The cache key to look up.

        Returns:
            A list of TimelineEntry objects if the cache is hit, otherwise None.
        """
        if not self.cache_enabled:
            return None
        cache_file = self.cache_dir / f"{cache_key}.json"
        if not cache_file.exists():
            return None
        try:
            cache_age = datetime.now(timezone.utc) - datetime.fromtimestamp(cache_file.stat().st_mtime, tz=timezone.utc)
            if cache_age > timedelta(hours=self.settings.CACHE_TTL_HOURS):
                log.debug(f"Cache expired for key {cache_key}, removing")
                cache_file.unlink()
                return None
            with open(cache_file, 'r') as f:
                cached_data = json.load(f)
            log.info(f"Using cached LLM response for key {cache_key}")
            return [TimelineEntry.model_validate(entry) for entry in cached_data]
        except Exception as e:
            log.warning(f"Failed to load cache for key {cache_key}: {e}")
            if cache_file.exists():
                try:
                    cache_file.unlink()
                except OSError as unlink_e:
                    log.error(f"Failed to unlink corrupted cache file {cache_file}: {unlink_e}")
            return None

    def save_to_cache(self, cache_key: str, entries: List[TimelineEntry]) -> None:
        """
        Saves an LLM response to the cache.

        Args:
            cache_key: The cache key to save the response under.
            entries: The list of TimelineEntry objects to save.
        """
        if not self.cache_enabled:
            return
        try:
            cache_file = self.cache_dir / f"{cache_key}.json"
            entries_data = [entry.model_dump(mode='json') for entry in entries]
            with open(cache_file, 'w') as f:
                json.dump(entries_data, f, indent=2)
            log.debug(f"Saved LLM response to cache with key {cache_key}")
        except Exception as e:
            log.warning(f"Failed to save to cache for key {cache_key}: {e}")


class LLMProcessor:
    """Handles LLM-based timeline enrichment."""

    def __init__(self, settings: ServiceSettingsType):
        self.settings = settings
        self.client = None
        self.cache = LLMResponseCache(settings)
        self._client_initialized = False

    def _initialize_client(self):
        """Lazy initialization of the LLM client."""
        if self._client_initialized:
            return

        try:
            api_key = self.settings.GEMINI_API_KEY
            if not api_key or api_key == "YOUR_API_KEY_HERE":
                raise ValueError("GEMINI_API_KEY not configured in service settings")

            self.client = genai.Client(api_key=api_key)
            self._client_initialized = True
            log.info(f"Gemini client initialized successfully with model target: {self.settings.ENRICHMENT_MODEL_NAME}")

        except Exception as e:
            log.error(f"Failed to initialize Gemini client: {e}. LLM processing will be disabled.", exc_info=True)
            self.client = None
            self._client_initialized = True

    def _build_prompt(self, events_df_chunk: pl.DataFrame, local_day: date, project_names: List[str]) -> str:
        if events_df_chunk.is_empty():
            return ""

        if project_names:
            project_list = ", ".join(f'"{name}"' for name in sorted(project_names))
        else:
            project_list = "No projects have been created yet."

        required_cols = ["time_display", "duration_s", "app", "title", "url"]
        missing_cols = [
            pl.lit("", dtype=pl.Utf8).alias(col)
            for col in required_cols
            if col not in events_df_chunk.columns
        ]
        if missing_cols:
            events_df_chunk = events_df_chunk.with_columns(missing_cols)

        events_table_md = (
            events_df_chunk.select(required_cols)
            .fill_null("")
            .to_pandas()
            .to_markdown(index=False)
        )
        schema_description = (
            '[{"start": "YYYY-MM-DDTHH:MM:SSZ", '
            '"end": "YYYY-MM-DDTHH:MM:SSZ", '
            '"activity": "string", '
            '"project": "string | null", '
            '"notes": "string | null"}]'
        )
        prompt = prompts.TIMELINE_ENRICHMENT_SYSTEM_PROMPT.format(
            day_iso=local_day.isoformat(),
            schema_description=schema_description,
            events_table_md=events_table_md,
            project_list=project_list
        )
        return prompt

    async def process_chunk_with_llm(self, events_df_chunk: pl.DataFrame, local_day: date, project_names: List[str]) -> List[TimelineEntry]:
        """
        Processes a chunk of events with the LLM to generate timeline entries.

        Args:
            events_df_chunk: The DataFrame of events to process.
            local_day: The local date of the events.
            project_names: A list of known project names to guide the LLM.

        Returns:
            A list of TimelineEntry objects generated by the LLM.
        """
        if events_df_chunk.is_empty():
            log.warning("Empty event chunk provided to LLM processor.")
            return []

        if not self._client_initialized:
            log.info("Initializing LLM client on first use...")
            self._initialize_client()

        if not self.client:
            log.error("LLM client not available. Cannot process chunk.")
            return []

        cache_key = self.cache._generate_cache_key(events_df_chunk, local_day, project_names)
        cached_response = self.cache.get_cached_response(cache_key)
        if cached_response is not None:
            return cached_response

        prompt_text = self._build_prompt(events_df_chunk, local_day, project_names)
        if not prompt_text:
            return []

        try:
            config = genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.3,
            )
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.settings.ENRICHMENT_MODEL_NAME,
                contents=prompt_text,
                config=config
            )

            if response.prompt_feedback and response.prompt_feedback.block_reason:
                log.error(f"Prompt blocked by Gemini: {response.prompt_feedback.block_reason}")
                return []

            if not response.text:
                log.warning("Empty response from LLM for chunk")
                return []

            cleaned_text = response.text.strip()
            if cleaned_text.startswith("```json"):
                cleaned_text = cleaned_text[7:].strip()
            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3].strip()

            try:
                timeline_data = json.loads(cleaned_text)

                # Hotfix: Prepend date to time-only strings from LLM
                for entry in timeline_data:
                    for key in ['start', 'end']:
                        if key in entry and isinstance(entry[key], str):
                            # If 'T' is not in the string, it's likely a time-only value.
                            if 'T' not in entry[key].upper():
                                original_time = entry[key]
                                entry[key] = f"{local_day.isoformat()}T{original_time}"
                                log.warning(f"Corrected partial timestamp from LLM. Original: '{original_time}', New: '{entry[key]}'")

                entries = [TimelineEntry.model_validate(entry) for entry in timeline_data]
                self.cache.save_to_cache(cache_key, entries)
                return entries
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                log.error(f"Failed to parse LLM JSON response for chunk: {e}. Response text: {response.text[:500]}")
                return []

        except Exception as e:
            log.error(f"LLM processing failed for chunk on {local_day}: {e}", exc_info=True)
            return []