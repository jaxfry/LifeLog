import polars as pl

def segments_from_events(df: pl.DataFrame, gap_threshold_s: int = 20, min_session_s: int = 5) -> pl.DataFrame:
    #sort by time
    df = df.sort("timestamp")

    # Calc time gap to previous row
    df = df.with_columns([
        pl.col("timestamp").diff().alias("gap_to_prev"),
        (pl.col("app") != pl.col("app").shift()).alias("app_changed"),
        (pl.col("title") != pl.col("title").shift()).alias("title_changed"),
    ])

    # mark new session start
    df = df.with_columns([
        ((pl.col("gap_to_prev") > gap_threshold_s * 1000) |
         pl.col("app_changed") |
         pl.col("title_changed")).fill_null(True).alias("is_new_session")
    ])

    # Assign session ID by cumulative sum
    df = df.with_columns([
        pl.col("is_new_session").cast(pl.Int32).cum_sum().alias("session_id")
    ])
    # Group by session and aggregate
    segments = (
        df.group_by("session_id")
          .agg([
              pl.col("timestamp").min().alias("start"),
              (pl.col("timestamp") + pl.col("duration")).max().alias("end"),
              pl.col("duration").sum().alias("duration"),
              pl.col("app").first(),
              pl.col("title").first()
          ])
          .filter(pl.col("duration") >= min_session_s * 1000)
          .sort("start")
    )

    return segments