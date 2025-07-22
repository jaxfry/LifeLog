# central_server/processing_service/tests/test_event_aggregation.py
import unittest
from unittest.mock import MagicMock
import polars as pl
from polars.testing import assert_frame_equal
from datetime import datetime, timedelta, timezone

from central_server.processing_service.logic.event_aggregation import EventAggregator
from central_server.processing_service.models import ProcessingEventData

class TestEventAggregator(unittest.TestCase):

    def setUp(self):
        self.settings = MagicMock()
        self.settings.AFK_APP_NAME = "afk"
        self.settings.ENRICHMENT_MIN_DURATION_S = 10
        self.settings.ENRICHMENT_PROMPT_TRUNCATE_LIMIT = 50
        self.aggregator = EventAggregator(self.settings)

    def test_aggregate_events_from_data_empty_list(self):
        """Test aggregation with an empty list of events."""
        result_df = self.aggregator.aggregate_events_from_data([])
        self.assertTrue(result_df.is_empty())

    def test_aggregate_events_from_data_all_afk(self):
        """Test aggregation with only AFK events."""
        events_data = [
            ProcessingEventData(
                start_time=datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                end_time=datetime(2023, 1, 1, 12, 0, 5, tzinfo=timezone.utc),
                duration_s=5.0,
                app=self.settings.AFK_APP_NAME,
                title="AFK",
                url=None,
                event_type="afk",
            )
        ]
        result_df = self.aggregator.aggregate_events_from_data(events_data)
        self.assertTrue(result_df.is_empty())

    def test_aggregate_events_from_data_duration_filter(self):
        """Test that events shorter than min duration are filtered out."""
        events_data = [
            ProcessingEventData(
                start_time=datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                end_time=datetime(2023, 1, 1, 12, 0, 5, tzinfo=timezone.utc),
                duration_s=5.0,
                app="VSCode",
                title="Coding",
                url=None,
                event_type="window",
            )
        ]
        result_df = self.aggregator.aggregate_events_from_data(events_data)
        self.assertTrue(result_df.is_empty())

    def test_aggregate_events_from_data_truncation(self):
        """Test that long titles and URLs are truncated."""
        long_string = "a" * 100
        events_data = [
            ProcessingEventData(
                start_time=datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                end_time=datetime(2023, 1, 1, 12, 0, 15, tzinfo=timezone.utc),
                duration_s=15.0,
                app="Chrome",
                title=long_string,
                url=f"http://{long_string}.com",
                event_type="web",
            )
        ]
        result_df = self.aggregator.aggregate_events_from_data(events_data)
        self.assertEqual(len(result_df["title"][0]), self.settings.ENRICHMENT_PROMPT_TRUNCATE_LIMIT + 1)
        self.assertEqual(result_df["title"][0][-1], "…")
        self.assertEqual(len(result_df["url"][0]), self.settings.ENRICHMENT_PROMPT_TRUNCATE_LIMIT + 1)
        self.assertEqual(result_df["url"][0][-1], "…")

    def test_aggregate_events_from_data_successful_aggregation(self):
        """Test a successful aggregation with valid data."""
        start_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        events_data = [
            ProcessingEventData(
                start_time=start_time,
                end_time=start_time + timedelta(seconds=20), duration_s=20.0,
                app="VSCode", title="Working on tests", url=None,
                event_type="window"
            ),
            ProcessingEventData(
                start_time=start_time + timedelta(minutes=1),
                end_time=start_time + timedelta(minutes=1, seconds=5), duration_s=5.0,
                app="Chrome", title="Checking docs", url="http://docs.python.org",
                event_type="web"
            )
        ]
        
        # Set min duration to 0 to include the second event
        self.settings.ENRICHMENT_MIN_DURATION_S = 0
        aggregator = EventAggregator(self.settings)
        result_df = aggregator.aggregate_events_from_data(events_data)

        expected_df = pl.DataFrame({
            "time_display": ["12:00:00", "12:01:00"],
            "duration_s": [20, 5],
            "app": ["VSCode", "Chrome"],
            "title": ["Working on tests", "Checking docs"],
            "url": ["", "http://docs.python.org"],
        })

        # Select only columns that are expected
        result_df_selected = result_df.select(["time_display", "duration_s", "app", "title", "url"])
        
        assert_frame_equal(result_df_selected, expected_df, check_dtypes=False)

if __name__ == '__main__':
    unittest.main()