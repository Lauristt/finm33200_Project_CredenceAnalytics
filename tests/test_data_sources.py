import unittest
import urllib.error
from datetime import date
from unittest.mock import patch

from financial_credibility.config import ToolkitConfig
from financial_credibility.data_sources import FreeDataSourceClient, _price_provider_symbols
from financial_credibility.models import ArgumentType
from financial_credibility.price_history import (
    infer_price_window,
    PricePoint,
    needs_historical_price_data,
    parse_lookback_months,
    summarize_price_history,
)


class DataSourceClientTests(unittest.TestCase):
    def test_sec_concepts_for_revenue_claim(self):
        client = FreeDataSourceClient(ToolkitConfig())
        concepts = client._concepts_for_claim("Apple revenue grew 6% year over year.")
        self.assertIn("Revenues", concepts)

    def test_sec_company_facts_not_used_for_acquisition_claim(self):
        client = FreeDataSourceClient(ToolkitConfig())

        self.assertEqual(client._concepts_for_claim("SMBC acquired Jefferies in 2026."), [])
        self.assertEqual(client._concepts_for_claim("三井住友银行2026年收购Jefferies。"), [])

    def test_sec_concept_matcher_handles_custom_revenue_tags(self):
        client = FreeDataSourceClient(ToolkitConfig())
        facts = {
            "us-gaap": {"Revenues": {"units": {"USD": []}}},
            "nvda": {"DataCenterRevenue": {"units": {"USD": []}}},
        }

        matches = client._matching_sec_concepts(
            facts,
            ["Revenues"],
            "NVIDIA data center revenue represented more than 80% of total revenue.",
        )

        self.assertEqual([concept for concept, _ in matches], ["Revenues", "DataCenterRevenue"])

    def test_fred_series_for_macro_claim(self):
        client = FreeDataSourceClient(ToolkitConfig(fred_api_key="demo"))
        self.assertEqual(client._fred_series_for_claim("Inflation is falling."), "CPIAUCSL")
        examples = {
            "SOFR rose yesterday.": "SOFR",
            "The 2-year Treasury yield moved higher.": "DGS2",
            "The 30Y Treasury yield fell.": "DGS30",
            "Core PCE inflation slowed.": "PCEPILFE",
            "Nonfarm payrolls increased.": "PAYEMS",
            "HY OAS widened.": "BAMLH0A0HYM2",
            "IG OAS tightened.": "BAMLC0A0CM",
            "WTI crude oil prices rose.": "DCOILWTICO",
            "Brent crude oil prices rose.": "DCOILBRENTEU",
            "Gold prices increased.": "GOLDAMGBD228NLBM",
            "EUR/USD strengthened.": "DEXUSEU",
            "The dollar index declined.": "DTWEXBGS",
        }
        for claim, series_id in examples.items():
            with self.subTest(claim=claim):
                self.assertEqual(client._fred_series_for_claim(claim), series_id)

    def test_fred_series_keyword_matching_avoids_embedded_words(self):
        client = FreeDataSourceClient(ToolkitConfig(fred_api_key="demo"))

        self.assertIsNone(client._fred_series_for_claim("Corporate revenue improved."))

    def test_fred_request_respects_as_of_date(self):
        client = FakeDataSourceClient(
            ToolkitConfig(fred_api_key="demo"),
            json_payload={"observations": [{"date": "2024-03-01", "value": "3.2"}]},
        )

        results = client.fred("Inflation is falling.", as_of_date="2024-03-31")

        self.assertEqual(results[0].raw["provider"], "fred")
        self.assertIn("observation_end=2024-03-31", client.last_url)

    def test_fred_historical_prices_parses_index_levels(self):
        client = FakeDataSourceClient(
            ToolkitConfig(fred_api_key="demo"),
            json_payload={
                "observations": [
                    {"date": "2026-05-25", "value": "."},
                    {"date": "2026-05-26", "value": "7519.12"},
                ]
            },
        )

        points = client.fred_historical_prices("SPX", date(2026, 5, 25), date(2026, 5, 26))

        self.assertEqual(len(points), 1)
        self.assertEqual(points[0].date, date(2026, 5, 26))
        self.assertEqual(points[0].close, 7519.12)
        self.assertIn("series_id=SP500", client.last_url)
        self.assertIn("observation_start=2026-05-25", client.last_url)

    def test_bls_api_posts_v2_timeseries_request(self):
        client = FakeDataSourceClient(
            ToolkitConfig(bls_api_key="bls-key"),
            post_payload={
                "Results": {
                    "series": [
                        {
                            "seriesID": "CUSR0000SA0",
                            "data": [
                                {"year": "2026", "period": "M04", "periodName": "April", "value": "319.1"},
                                {"year": "2026", "period": "M03", "periodName": "March", "value": "318.8"},
                            ],
                        }
                    ]
                }
            },
        )

        results = client.bls_api("BLS CPI increased.", as_of_date="2026-05-27")

        self.assertEqual(results[0].raw["provider"], "bls_api")
        self.assertEqual(results[0].raw["series_id"], "CUSR0000SA0")
        self.assertEqual(client.last_url, "https://api.bls.gov/publicAPI/v2/timeseries/data/")
        self.assertEqual(client.last_post_body["registrationkey"], "bls-key")
        self.assertEqual(client.last_post_body["seriesid"], ["CUSR0000SA0"])
        self.assertIn("2026-M04: 319.1", results[0].snippet)

    def test_bea_api_builds_nipa_request(self):
        client = FakeDataSourceClient(
            ToolkitConfig(bea_api_key="bea-key"),
            json_payload={
                "BEAAPI": {
                    "Results": {
                        "Data": [
                            {
                                "TableName": "T10101",
                                "LineNumber": "1",
                                "LineDescription": "Gross domestic product",
                                "TimePeriod": "2025Q4",
                                "DataValue": "2.4",
                            },
                            {
                                "TableName": "T10101",
                                "LineNumber": "2",
                                "LineDescription": "Personal consumption expenditures",
                                "TimePeriod": "2025Q4",
                                "DataValue": "3.1",
                            },
                        ]
                    }
                }
            },
        )

        results = client.bea_api("BEA GDP grew in 2025.", as_of_date="2025-12-31")

        self.assertEqual(results[0].raw["provider"], "bea_api")
        self.assertEqual(results[0].raw["table_name"], "T10101")
        self.assertIn("method=GetData", client.last_url)
        self.assertIn("UserID=bea-key", client.last_url)
        self.assertIn("2025Q4: 2.4", results[0].snippet)
        self.assertNotIn("3.1", results[0].snippet)

    def test_eia_api_builds_api_v2_request(self):
        client = FakeDataSourceClient(
            ToolkitConfig(eia_api_key="eia-key"),
            json_payload={
                "response": {
                    "data": [
                        {
                            "period": "2026-05-20",
                            "series": "RWTC",
                            "series-description": "Cushing, OK WTI Spot Price FOB",
                            "value": 62.5,
                            "units": "dollars per barrel",
                        }
                    ]
                }
            },
        )

        results = client.eia_api("EIA WTI crude oil price rose.", as_of_date="2026-05-27")

        self.assertEqual(results[0].raw["provider"], "eia_api")
        self.assertEqual(results[0].raw["series_id"], "RWTC")
        self.assertIn("https://api.eia.gov/v2/petroleum/pri/spt/data/?", client.last_url)
        self.assertIn("api_key=eia-key", client.last_url)
        self.assertIn("facets%5Bseries%5D%5B%5D=RWTC", client.last_url)
        self.assertIn("2026-05-20: 62.5", results[0].snippet)

    def test_market_index_symbols_map_to_price_provider_aliases(self):
        self.assertEqual(_price_provider_symbols("SPX", "stooq_historical_prices")[0], "^spx")
        self.assertEqual(_price_provider_symbols("NDQ", "fmp_historical_prices")[0], "^IXIC")
        self.assertEqual(_price_provider_symbols("DJIA", "finnhub_historical_prices")[0], "^DJI")
        self.assertEqual(_price_provider_symbols("RUT", "stooq")[0], "iwm.us")

    def test_stooq_latest_quote_uses_index_symbol_mapping(self):
        client = FakeDataSourceClient(
            ToolkitConfig(),
            text_payload=(
                "Symbol,Date,Time,Open,High,Low,Close,Volume\n"
                "^SPX,2026-05-27,22:00:00,7526.00,7530.70,7499.70,7520.40,3120497619\n"
            ),
        )

        results = client.stooq("SPX")

        self.assertEqual(len(results), 1)
        self.assertIn("S&P 500 Index", results[0].title)
        self.assertIn("S&P 500 Index (SPX) latest quote", results[0].snippet)
        self.assertIn("s=%5Espx", client.last_url)
        self.assertEqual(results[0].raw["symbol"], "^spx")
        self.assertEqual(results[0].raw["requested_symbol"], "SPX")

    def test_stooq_latest_quote_does_not_verify_after_as_of_date(self):
        client = FakeDataSourceClient(
            ToolkitConfig(),
            text_payload=(
                "Symbol,Date,Time,Open,High,Low,Close,Volume\n"
                "^SPX,2026-05-27,22:00:00,7526.00,7530.70,7499.70,7520.40,3120497619\n"
            ),
        )

        self.assertEqual(client.stooq("SPX", as_of_date="2026-05-26"), [])

    def test_query_notes_missing_historical_price_series(self):
        client = FakeDataSourceClient(
            ToolkitConfig(),
            text_payload=(
                "Symbol,Date,Time,Open,High,Low,Close,Volume\n"
                "^SPX,2026-05-27,22:00:00,7526.00,7530.70,7499.70,7520.40,3120497619\n"
            ),
        )

        results, notes = client.query(
            claim="The S&P 500 rose 0.6% Tuesday.",
            ticker="SPX",
            argument_type=ArgumentType.METRIC_FACT,
            allowed_sources=["historical_prices"],
            as_of_date="2026-05-26",
        )

        self.assertEqual(results, [])
        self.assertTrue(any("historical_prices: no historical price series returned" in note for note in notes))

    def test_return_claim_does_not_fallback_to_latest_quote(self):
        client = FakeDataSourceClient(
            ToolkitConfig(),
            text_payload=(
                "Symbol,Date,Time,Open,High,Low,Close,Volume\n"
                "SNOW.US,2026-05-28,22:00:00,237.00,242.11,229.49,239.19,16105887\n"
            ),
        )

        results, notes = client.query(
            claim="Snowflake rose 34.1% after profit.",
            ticker="SNOW",
            argument_type=ArgumentType.METRIC_FACT,
            allowed_sources=["historical_prices", "market_prices_vendor"],
            as_of_date="2026-05-28",
        )

        self.assertEqual(results, [])
        self.assertTrue(any("historical_prices: no historical price series returned" in note for note in notes))

    def test_sec_company_facts_filters_filings_after_as_of_date(self):
        payload = {
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {
                            "USD": [
                                {
                                    "start": "2023-01-01",
                                    "end": "2023-12-31",
                                    "val": 100,
                                    "filed": "2024-02-01",
                                    "form": "10-K",
                                },
                                {
                                    "start": "2024-01-01",
                                    "end": "2024-12-31",
                                    "val": 200,
                                    "filed": "2025-02-01",
                                    "form": "10-K",
                                },
                            ]
                        }
                    }
                }
            }
        }
        client = FakeDataSourceClient(ToolkitConfig(), json_payload=payload)

        with patch.object(client, "_ticker_to_cik", return_value=320193):
            results = client.sec_company_facts("Apple revenue.", "AAPL", as_of_date="2025-01-15")

        self.assertEqual(len(results), 1)
        self.assertIn("100", results[0].snippet)
        self.assertNotIn("200", results[0].snippet)

    def test_world_bank_indicators_builds_v2_no_key_request(self):
        client = FreeDataSourceClient(ToolkitConfig(world_bank_base_url="https://api.worldbank.org/v2"))
        payload = [
            {"page": 1, "pages": 1, "per_page": 500, "total": 2},
            [
                {
                    "indicator": {"id": "NY.GDP.MKTP.CD", "value": "GDP (current US$)"},
                    "country": {"id": "CN", "value": "China"},
                    "countryiso3code": "CHN",
                    "date": "2023",
                    "value": 17794781698646.0,
                    "unit": "",
                },
                {
                    "indicator": {"id": "NY.GDP.MKTP.CD", "value": "GDP (current US$)"},
                    "country": {"id": "CN", "value": "China"},
                    "countryiso3code": "CHN",
                    "date": "2022",
                    "value": 17963171479205.0,
                    "unit": "",
                },
            ],
        ]

        with patch.object(client, "_get_json", return_value=payload) as get_json:
            results = client.world_bank_indicators("China GDP from 2015 to 2023")

        self.assertEqual(len(results), 1)
        url = get_json.call_args.args[0]
        self.assertIn("/country/CN/indicator/NY.GDP.MKTP.CD?", url)
        self.assertIn("format=json", url)
        self.assertIn("date=2015%3A2023", url)
        self.assertIn("per_page=500", url)
        self.assertEqual(results[0].source, "World Bank Indicators API")
        self.assertEqual(results[0].raw["provider"], "world_bank_indicators")
        self.assertEqual(results[0].raw["country"], "CN")
        self.assertEqual(results[0].raw["indicator"], "NY.GDP.MKTP.CD")

    def test_world_bank_indicators_does_not_fire_without_country_or_context(self):
        client = FreeDataSourceClient(ToolkitConfig())

        with patch.object(client, "_get_json") as get_json:
            results = client.world_bank_indicators("GDP increased last year.")

        self.assertEqual(results, [])
        get_json.assert_not_called()

    def test_price_pattern_claim_needs_historical_prices(self):
        claim = "Nvidia's stock price seems like oscillating these months (10 months)."
        self.assertTrue(needs_historical_price_data(claim))
        self.assertEqual(parse_lookback_months(claim), 10)

    def test_sec_company_facts_does_not_fetch_without_concept_mapping(self):
        client = FreeDataSourceClient(ToolkitConfig())

        with patch.object(client, "_ticker_to_cik") as ticker_to_cik, patch.object(client, "_get_json") as get_json:
            results = client.sec_company_facts(
                "Nvidia said its supply rose to $119 billion in the fiscal first quarter.",
                "NVDA",
            )

        self.assertEqual(results, [])
        ticker_to_cik.assert_not_called()
        get_json.assert_not_called()

    def test_single_name_price_move_claim_needs_historical_prices(self):
        claim = "Qualcomm fell 6% after sharp gains on Tuesday."
        self.assertTrue(needs_historical_price_data(claim))
        self.assertEqual(parse_lookback_months(claim), 1)
        self.assertTrue(needs_historical_price_data("The S&P 500 added 0.6% Tuesday."))
        self.assertTrue(needs_historical_price_data("The Dow Jones Industrial Average slipped 0.2%."))
        self.assertFalse(needs_historical_price_data("Qualcomm revenue fell 6% year over year."))
        self.assertFalse(needs_historical_price_data("Nvidia supply rose to $119 billion in the fiscal first quarter."))

    def test_price_window_infers_single_session_recent_and_ytd_contexts(self):
        session = infer_price_window("The S&P 500 added 0.6% Tuesday.", date(2026, 5, 26))
        recent = infer_price_window("Qualcomm fell 6% after sharp gains recently.", date(2026, 5, 26))
        ytd = infer_price_window("For the year, the S&P 500 is up 673.62 points, or 9.8%.", date(2026, 5, 26))

        self.assertEqual(session.source, "single_session_context")
        self.assertEqual(session.start, date(2026, 5, 19))
        self.assertEqual(recent.source, "approximate_recent_context")
        self.assertEqual(recent.lookback_months, 1)
        self.assertEqual(ytd.source, "ytd_context")
        self.assertEqual(ytd.start, date(2026, 1, 1))
        self.assertTrue(needs_historical_price_data("For the year, the S&P 500 is up 673.62 points, or 9.8%."))

    def test_historical_prices_uses_inferred_ytd_window(self):
        client = FakeDataSourceClient(
            ToolkitConfig(),
            text_payload=(
                "Date,Open,High,Low,Close,Volume\n"
                "2026-01-02,100,101,99,100,1000\n"
                "2026-05-26,109.8,110,109,109.8,1000\n"
            ),
        )

        results = client.historical_prices(
            "SPX",
            "For the year, the S&P 500 is up 673.62 points, or 9.8%.",
            as_of_date="2026-05-26",
        )

        self.assertEqual(len(results), 1)
        self.assertIn("d1=20260101", client.last_url)
        self.assertIn("d2=20260526", client.last_url)
        self.assertEqual(results[0].raw["window_source"], "ytd_context")
        self.assertIn("retrieval_window year to date", results[0].snippet)

    def test_price_history_summary_detects_oscillation(self):
        points = [
            PricePoint(date(2025, 1, 31), 100, 101, 99, 100),
            PricePoint(date(2025, 2, 28), 130, 131, 129, 130),
            PricePoint(date(2025, 3, 31), 95, 96, 94, 95),
            PricePoint(date(2025, 4, 30), 125, 126, 124, 125),
            PricePoint(date(2025, 5, 31), 90, 91, 89, 90),
            PricePoint(date(2025, 6, 30), 120, 121, 119, 120),
        ]
        summary = summarize_price_history(points)

        self.assertIsNotNone(summary)
        self.assertGreaterEqual(summary.monthly_direction_changes, 3)
        self.assertIn(summary.oscillation_signal, {"moderate", "strong"})

    def test_price_history_summary_includes_latest_daily_returns(self):
        points = [
            PricePoint(date(2026, 5, 18), 100, 101, 99, 100),
            PricePoint(date(2026, 5, 19), 108, 109, 107, 108),
            PricePoint(date(2026, 5, 20), 101.52, 102, 101, 101.52),
        ]
        summary = summarize_price_history(points)

        self.assertIsNotNone(summary)
        self.assertEqual(summary.previous_close, 108)
        self.assertEqual(summary.latest_daily_point_change, -6.48)
        self.assertEqual(summary.latest_daily_abs_point_change, 6.48)
        self.assertEqual(summary.latest_daily_return_pct, -6.0)
        self.assertEqual(summary.latest_daily_abs_return_pct, 6.0)
        self.assertEqual(summary.previous_daily_return_pct, 8.0)

    def test_cftc_cot_adapter_extracts_public_reporting_rows(self):
        client = FakeDataSourceClient(
            ToolkitConfig(cftc_app_token="token"),
            json_payload=[
                {
                    "report_date_as_yyyy_mm_dd": "2026-05-19",
                    "market_and_exchange_names": "GOLD - COMMODITY EXCHANGE INC.",
                    "open_interest_all": "512345",
                    "noncomm_positions_long_all": "210000",
                    "noncomm_positions_short_all": "95000",
                }
            ],
        )

        results = client.cftc_cot("CFTC COT data showed gold open interest rose.")

        self.assertEqual(results[0].raw["provider"], "cftc_cot")
        self.assertIn("GOLD", results[0].snippet)
        self.assertIn("%24%24app_token=token", client.last_url)

    def test_ecb_bis_and_boe_csv_adapters_extract_observations(self):
        csv_text = "TIME_PERIOD,OBS_VALUE\n2026-05,2.50\n2026-04,2.75\n"

        ecb = FakeDataSourceClient(ToolkitConfig(), text_payload=csv_text).ecb_data_portal(
            "ECB deposit facility rate was cut."
        )[0]
        bis_client = FakeDataSourceClient(ToolkitConfig(), text_payload=csv_text)
        bis = bis_client.bis_data_portal("BIS cross-border banking claims increased.")[0]
        boe_client = FakeDataSourceClient(
            ToolkitConfig(),
            text_payload="DATE,IUDBEDR\n01 Jan 2026,3.75\n01 Dec 2025,4.00\n",
        )
        boe = boe_client.bank_of_england("Bank of England Bank Rate changed.")[0]

        self.assertEqual(ecb.raw["provider"], "ecb_data_portal")
        self.assertEqual(bis.raw["provider"], "bis_data_portal")
        self.assertEqual(boe.raw["provider"], "bank_of_england")
        self.assertIn("2026-05: 2.50", ecb.snippet)
        self.assertIn("https://stats.bis.org/api/v2/data/dataflow/BIS/WS_LBS_D_PUB/1.0/", bis_client.last_url)
        self.assertIn("format=csv", bis_client.last_url)
        self.assertIn("csv.x=yes", boe_client.last_url)
        self.assertIn("CSVF=TN", boe_client.last_url)
        self.assertIn("Dateto=now", boe_client.last_url)
        self.assertIn("2026-01-01: 3.75", boe.snippet)

    def test_imf_data_api_builds_public_sdmx3_request(self):
        client = FakeDataSourceClient(
            ToolkitConfig(imf_base_url="https://api.imf.org/external/sdmx/3.0"),
            json_payload={
                "data": {
                    "dataSets": [
                        {
                            "series": {
                                "0:0:0": {
                                    "observations": {
                                        "0": [1.8],
                                        "1": [2.8],
                                        "2": [2.1],
                                    }
                                }
                            }
                        }
                    ],
                    "structures": {
                        "dimensions": {
                            "observation": [
                                [
                                    {
                                        "id": "TIME_PERIOD",
                                        "values": [{"id": "2031"}, {"id": "2025"}, {"id": "2024"}],
                                    }
                                ]
                            ]
                        }
                    },
                }
            },
        )

        results = client.imf_data_api("IMF WEO US GDP growth from 2024 to 2025")

        self.assertEqual(results[0].raw["provider"], "imf_data_api")
        self.assertEqual(results[0].raw["agency"], "IMF.RES")
        self.assertEqual(results[0].raw["dataflow"], "WEO")
        self.assertEqual(results[0].raw["key"], "USA.NGDP_RPCH.A")
        self.assertIn("/data/dataflow/IMF.RES/WEO/+/USA.NGDP_RPCH.A?", client.last_url)
        self.assertIn("startPeriod=2024", client.last_url)
        self.assertIn("endPeriod=2025", client.last_url)
        self.assertIn("2025: 2.8", results[0].snippet)
        self.assertNotIn("2031", results[0].snippet)

    def test_world_bank_indicator_adapter_extracts_country_observations(self):
        client = FakeDataSourceClient(
            ToolkitConfig(),
            json_payload=[
                {"page": 1},
                [
                    {"date": "2025", "value": 30500000000000, "country": {"value": "United States"}},
                    {"date": "2024", "value": 29000000000000, "country": {"value": "United States"}},
                ],
            ],
        )

        results = client.world_bank_indicators("World Bank US GDP increased.")

        self.assertEqual(results[0].raw["provider"], "world_bank_indicators")
        self.assertEqual(results[0].raw["country"], "US")
        self.assertEqual(results[0].raw["indicator"], "NY.GDP.MKTP.CD")
        self.assertIn("2025", results[0].snippet)

    def test_openfigi_adapter_posts_optional_key_and_extracts_mapping(self):
        client = FakeDataSourceClient(
            ToolkitConfig(openfigi_api_key="figi-key"),
            post_payload=[
                {
                    "data": [
                        {
                            "ticker": "AAPL",
                            "name": "Apple Inc",
                            "figi": "BBG000B9XRY4",
                            "compositeFIGI": "BBG000B9XRY4",
                            "securityType": "Common Stock",
                            "marketSector": "Equity",
                        }
                    ]
                }
            ],
        )

        results = client.openfigi("Map AAPL to FIGI.", "AAPL")

        self.assertEqual(results[0].raw["provider"], "openfigi")
        self.assertIn("BBG000B9XRY4", results[0].snippet)
        self.assertEqual(client.last_post_body[0]["idType"], "TICKER")
        self.assertEqual(client.last_post_headers["X-OPENFIGI-APIKEY"], "figi-key")

    def test_finra_query_api_gets_oauth_token_and_dataset_rows(self):
        client = FakeDataSourceClient(
            ToolkitConfig(finra_client_id="client-id", finra_client_secret="client-secret"),
            json_payload=[
                {
                    "tradeReportDate": "2026-05-26",
                    "productCategory": "all securities",
                    "totalTrades": 1746,
                    "advances": 1018,
                    "declines": 592,
                    "totalVolume": 11093.5282,
                }
            ],
            form_payload={"access_token": "token-123", "expires_in": "43170", "token_type": "Bearer"},
        )

        results = client.finra_query_api("FINRA TRACE corporate bond trading volumes increased.")

        self.assertEqual(results[0].raw["provider"], "finra_query_api")
        self.assertEqual(results[0].raw["group"], "fixedIncomeMarket")
        self.assertEqual(results[0].raw["dataset"], "corporateMarketSentiment")
        self.assertIn("https://api.finra.org/data/group/fixedIncomeMarket/name/corporateMarketSentiment?", client.last_url)
        self.assertIn("limit=5", client.last_url)
        self.assertEqual(client.last_get_headers["Authorization"], "Bearer token-123")
        self.assertEqual(client.last_form_url, "https://ews.fip.finra.org/fip/rest/ews/oauth2/access_token")
        self.assertEqual(client.last_form_body["grant_type"], "client_credentials")
        self.assertTrue(client.last_form_headers["Authorization"].startswith("Basic "))
        self.assertIn("totalTrades 1746", results[0].snippet)

    def test_finra_query_api_returns_entitlement_diagnostic_on_403(self):
        client = FakeDataSourceClient(
            ToolkitConfig(finra_client_id="client-id", finra_client_secret="client-secret"),
            json_payload=urllib.error.HTTPError(
                "https://api.finra.org/data/group/fixedIncomeMarket/name/corporateMarketBreadth",
                403,
                "Forbidden",
                hdrs=None,
                fp=None,
            ),
            form_payload={"access_token": "token-123", "expires_in": "43170", "token_type": "Bearer"},
        )

        results = client.finra_query_api("FINRA TRACE corporate bond market breadth changed.")

        self.assertEqual(results[0].raw["provider"], "finra_query_api")
        self.assertEqual(results[0].raw["status_code"], 403)
        self.assertEqual(results[0].raw["error"], "finra_entitlement_or_authorization")
        self.assertIn("not be entitled", results[0].snippet)


class FakeDataSourceClient(FreeDataSourceClient):
    def __init__(
        self,
        config: ToolkitConfig,
        json_payload=None,
        text_payload: str = "",
        post_payload=None,
        form_payload=None,
    ):
        super().__init__(config)
        self.json_payload = json_payload
        self.text_payload = text_payload
        self.post_payload = post_payload
        self.form_payload = form_payload
        self.last_url = ""
        self.last_post_body = None
        self.last_post_headers = None
        self.last_form_url = ""
        self.last_form_body = None
        self.last_form_headers = None
        self.last_get_headers = None

    def _get_json(self, url: str, sec: bool = False):
        self.last_url = url
        return self.json_payload

    def _get_json_with_headers(self, url: str, headers=None):
        self.last_url = url
        self.last_get_headers = headers or {}
        if isinstance(self.json_payload, Exception):
            raise self.json_payload
        return self.json_payload

    def _get_text(self, url: str, sec: bool = False) -> str:
        self.last_url = url
        return self.text_payload

    def _post_json(self, url: str, body, headers=None):
        self.last_url = url
        self.last_post_body = body
        self.last_post_headers = headers or {}
        return self.post_payload

    def _post_form_json(self, url: str, body, headers=None):
        self.last_form_url = url
        self.last_form_body = body
        self.last_form_headers = headers or {}
        return self.form_payload


if __name__ == "__main__":
    unittest.main()
