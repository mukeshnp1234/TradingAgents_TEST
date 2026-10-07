import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from scripts.export_yahoo_ohlcv import (
    OHLCV_COLUMNS,
    default_output_path,
    shape_history,
    sheet_name,
)


@pytest.mark.unit
class ExportYahooOhlcvTests(unittest.TestCase):
    def test_shape_history_drops_timezone_and_keeps_ohlcv_columns(self):
        index = pd.DatetimeIndex(
            [
                datetime(2024, 1, 3, tzinfo=ZoneInfo("Asia/Kolkata")),
                datetime(2024, 1, 2, tzinfo=ZoneInfo("Asia/Kolkata")),
            ],
            name="Date",
        )
        raw = pd.DataFrame(
            {
                "Open": [10.123, 9.5],
                "High": [11.0, 10.0],
                "Low": [9.876, 9.0],
                "Close": [10.5, 9.8],
                "Adj Close": [10.456, 9.789],
                "Volume": [1000.4, 2000],
                "Dividends": [0.0, 0.0],
            },
            index=index,
        )

        shaped = shape_history(raw)

        self.assertEqual(list(shaped.columns), OHLCV_COLUMNS)
        self.assertEqual(shaped["Date"].iloc[0], pd.Timestamp("2024-01-02"))
        self.assertIsNone(shaped["Date"].dt.tz)
        self.assertEqual(shaped["Open"].iloc[1], 10.12)
        self.assertEqual(shaped["Adj Close"].iloc[0], 9.79)
        self.assertEqual(int(shaped["Volume"].iloc[1]), 1000)
        self.assertNotIn("Dividends", shaped.columns)

    def test_shape_history_fills_adj_close_from_close(self):
        raw = pd.DataFrame(
            {
                "Open": [1.0],
                "High": [2.0],
                "Low": [0.5],
                "Close": [1.5],
                "Volume": [10],
            },
            index=pd.DatetimeIndex([pd.Timestamp("2020-01-01")], name="Datetime"),
        )

        shaped = shape_history(raw)

        self.assertEqual(shaped["Date"].iloc[0], pd.Timestamp("2020-01-01"))
        self.assertEqual(shaped["Adj Close"].iloc[0], 1.5)

    def test_shape_history_empty_frame_has_expected_columns(self):
        shaped = shape_history(pd.DataFrame())
        self.assertTrue(shaped.empty)
        self.assertEqual(list(shaped.columns), OHLCV_COLUMNS)

    def test_sheet_name_strips_invalid_characters_and_caps_length(self):
        self.assertEqual(sheet_name("HDFCBANK.NS"), "HDFCBANK.NS")
        self.assertEqual(sheet_name("BAD/NAME"), "BAD-NAME")
        self.assertEqual(len(sheet_name("X" * 40)), 31)

    def test_default_output_path_uses_symbol_or_combined_name(self):
        self.assertEqual(
            default_output_path(["HDFCBANK.NS"]).as_posix(),
            "exports/HDFCBANK.NS_ohlcv.xlsx",
        )
        self.assertEqual(
            default_output_path(["HDFCBANK.NS", "RELIANCE.NS"]).as_posix(),
            "exports/ohlcv.xlsx",
        )


if __name__ == "__main__":
    unittest.main()
