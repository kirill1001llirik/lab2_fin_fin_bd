import sqlite3
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import app


class AppHarness:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.current_spec = app.CITY_SPEC

    ensure_connection = app.ReferenceApp.ensure_connection
    rollback_safely = app.ReferenceApp.rollback_safely
    fetch_rows = app.ReferenceApp.fetch_rows
    sorted_rows = app.ReferenceApp.sorted_rows
    add_history = app.ReferenceApp.add_history
    save_record = app.ReferenceApp.save_record
    get_history = app.ReferenceApp.get_history
    city_options = app.ReferenceApp.city_options
    validate_field_names = app.ReferenceApp.validate_field_names


class ValidationEdgeCaseTests(unittest.TestCase):
    def test_date_parser_accepts_required_and_internal_formats(self):
        cases = {
            "01.01.1900": "1900-01-01",
            "31.12.2099": "2099-12-31",
            " 05.06.2026 ": "2026-06-05",
            "2026-06-05": "2026-06-05",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(app.parse_date_input(raw), expected)

    def test_date_parser_rejects_calendar_impossibilities(self):
        for raw in ("", " ", "00.01.2024", "01.00.2024", "31.04.2024", "29.02.2023", "2024-02-30"):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    app.parse_date_input(raw)

    def test_decimal_parser_rounds_half_up(self):
        cases = {
            "1.234": "1.23",
            "1.235": "1.24",
            "1,235": "1.24",
            "-1.235": "-1.24",
            "999999999.999": "1000000000.00",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(app.parse_decimal_input(raw), expected)

    def test_decimal_parser_accepts_plain_numeric_variants(self):
        cases = {
            " 0012,30 ": "12.30",
            "+5": "5.00",
            "-5": "-5.00",
            "0": "0.00",
            ".5": "0.50",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(app.parse_decimal_input(raw), expected)

    def test_decimal_parser_rejects_bad_and_non_finite_values(self):
        for raw in ("", " ", "abc", "1,2,3", "NaN", "sNaN", "Infinity", "-Infinity"):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    app.parse_decimal_input(raw)

    def test_format_date_converts_iso_to_ui_format(self):
        self.assertEqual(app.format_date("2026-05-29"), "29.05.2026")
        self.assertEqual(app.format_date(None), "")
        self.assertEqual(app.format_date("bad"), "bad")

    def test_format_decimal_keeps_two_fraction_digits(self):
        self.assertEqual(app.format_decimal("12"), "12.00")
        self.assertEqual(app.format_decimal("12.3"), "12.30")
        self.assertEqual(app.format_decimal("12.345"), "12.35")

    def test_compact_text_boundary_lengths(self):
        self.assertEqual(app.compact_text("abc", limit=3), "abc")
        self.assertEqual(app.compact_text("abcd", limit=3), "ab…")
        self.assertEqual(app.compact_text("a\nb\tc"), "a b c")

    def test_current_timestamp_has_database_friendly_shape(self):
        timestamp = app.current_timestamp()
        self.assertRegex(timestamp, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")

    def test_dictionary_specs_are_internally_consistent(self):
        for spec in app.DICTIONARIES:
            with self.subTest(spec=spec.key):
                field_keys = {field.key for field in spec.fields}
                for column in spec.columns:
                    if column.key != "city_label":
                        self.assertIn(column.key, field_keys)
                self.assertTrue(spec.table)
                self.assertTrue(spec.pk.endswith("_id"))


class ReferenceModuleTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory(ignore_cleanup_errors=True)
        self.original_db_path = app.DB_PATH
        self.original_schema_path = app.SCHEMA_PATH
        app.DB_PATH = Path(self.temp_dir.name) / "test.sqlite3"
        app.SCHEMA_PATH = Path("schema.sql")
        app.initialize_database()
        self.conn = app.connect_db()
        self.harness = AppHarness(self.conn)

    def tearDown(self):
        try:
            self.conn.close()
        except sqlite3.Error:
            pass
        app.DB_PATH = self.original_db_path
        app.SCHEMA_PATH = self.original_schema_path
        self.temp_dir.cleanup()

    def city_values(self, suffix="A", **overrides):
        values = {
            "name": f"City {suffix}",
            "country": "Country",
            "foundation_date": "2000-01-02",
            "population": 1000,
            "area_km2": "10.50",
            "description": f"Description {suffix}",
        }
        values.update(overrides)
        return values

    def supplier_values(self, city_id=None, suffix="A", **overrides):
        if city_id is None:
            city_id = self.conn.execute("SELECT city_id FROM cities WHERE is_deleted = 0 LIMIT 1").fetchone()[0]
        values = {
            "name": f"Supplier {suffix}",
            "inn": f"INN{suffix}",
            "city_id": city_id,
            "contract_date": "2024-03-04",
            "employees_count": 5,
            "annual_budget": "1234.50",
            "address": f"Address {suffix}",
            "comment": f"Comment {suffix}",
        }
        values.update(overrides)
        return values

    def test_required_seed_data_and_lookup_ids(self):
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM cities").fetchone()[0], 3)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0], 3)

        duplicate_names = self.conn.execute(
            "SELECT COUNT(*) FROM (SELECT name FROM cities GROUP BY name HAVING COUNT(*) > 1)"
        ).fetchone()[0]
        labels, ids, selected_index = self.harness.city_options()

        self.assertGreaterEqual(duplicate_names, 1)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIsNone(selected_index)
        self.assertTrue(all("id" not in label.lower() for label in labels))

    def test_validation_rejects_impossible_dates_and_non_finite_decimals(self):
        self.assertEqual(app.parse_date_input("29.02.2024"), "2024-02-29")
        with self.assertRaises(ValueError):
            app.parse_date_input("30.02.2024")
        self.assertEqual(app.parse_decimal_input("1250,5"), "1250.50")
        for value in ("NaN", "Infinity", "-Infinity", "abc"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    app.parse_decimal_input(value)

    def test_typed_sorting(self):
        rows = self.harness.fetch_rows(app.CITY_SPEC)

        by_population = self.harness.sorted_rows(rows, "population", False)
        populations = [row["population"] for row in by_population]
        self.assertEqual(populations, sorted(populations))

        by_date = self.harness.sorted_rows(rows, "foundation_date", False)
        dates = [row["foundation_date"] for row in by_date]
        self.assertEqual(dates, sorted(dates))

        self.harness.current_spec = app.SUPPLIER_SPEC
        supplier_rows = self.harness.fetch_rows(app.SUPPLIER_SPEC)
        by_employees = self.harness.sorted_rows(supplier_rows, "employees_count", False)
        employees = [row["employees_count"] for row in by_employees]
        self.assertEqual(employees, sorted(employees))

        by_budget = self.harness.sorted_rows(supplier_rows, "annual_budget", False)
        budgets = [float(row["annual_budget"]) for row in by_budget]
        self.assertEqual(budgets, sorted(budgets))

        by_contract_date = self.harness.sorted_rows(supplier_rows, "contract_date", False)
        contract_dates = [row["contract_date"] for row in by_contract_date]
        self.assertEqual(contract_dates, sorted(contract_dates))

    def test_soft_delete_main_dictionary_keeps_dependent_rows(self):
        city_id = self.conn.execute("SELECT city_id FROM suppliers WHERE is_deleted = 0 LIMIT 1").fetchone()[0]
        suppliers_before = self.conn.execute("SELECT COUNT(*) FROM suppliers WHERE is_deleted = 0").fetchone()[0]

        self.harness.add_history(app.CITY_SPEC, "DELETE", city_id)
        self.conn.execute("UPDATE cities SET is_deleted = 1 WHERE city_id = ?", (city_id,))
        self.conn.commit()

        suppliers_after = self.conn.execute("SELECT COUNT(*) FROM suppliers WHERE is_deleted = 0").fetchone()[0]
        refs_to_deleted_city = self.conn.execute(
            "SELECT COUNT(*) FROM suppliers WHERE city_id = ? AND is_deleted = 0",
            (city_id,),
        ).fetchone()[0]

        self.assertEqual(suppliers_after, suppliers_before)
        self.assertGreaterEqual(refs_to_deleted_city, 1)

    def test_update_history_and_rollback_on_failed_update(self):
        supplier_id = self.conn.execute("SELECT supplier_id FROM suppliers LIMIT 1").fetchone()[0]
        old = self.conn.execute("SELECT * FROM suppliers WHERE supplier_id = ?", (supplier_id,)).fetchone()
        values = {
            "name": old["name"] + " X",
            "inn": old["inn"],
            "city_id": old["city_id"],
            "contract_date": old["contract_date"],
            "employees_count": old["employees_count"],
            "annual_budget": str(old["annual_budget"]),
            "address": old["address"],
            "comment": old["comment"],
        }

        self.harness.save_record(app.SUPPLIER_SPEC, values, supplier_id)
        history = self.harness.get_history(app.SUPPLIER_SPEC, supplier_id)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["name"], old["name"])

        city_id = self.conn.execute("SELECT city_id FROM cities WHERE is_deleted = 0 LIMIT 1").fetchone()[0]
        bad_city = {
            "name": "Bad",
            "country": "Bad",
            "foundation_date": "2024-01-01",
            "population": -1,
            "area_km2": "1.00",
            "description": "Bad",
        }
        with self.assertRaises(sqlite3.IntegrityError):
            self.harness.save_record(app.CITY_SPEC, bad_city, city_id)
        pending_history = self.conn.execute("SELECT COUNT(*) FROM city_history WHERE city_id = ?", (city_id,)).fetchone()[0]
        self.assertEqual(pending_history, 0)

    def test_reconnect_after_closed_sqlite_connection(self):
        self.conn.close()
        rows = self.harness.fetch_rows(app.CITY_SPEC)
        self.conn = self.harness.conn
        self.assertEqual(len(rows), 3)

    def test_specs_match_required_two_dictionary_model(self):
        self.assertEqual(len(app.DICTIONARIES), 2)
        self.assertEqual(app.CITY_SPEC.key, "cities")
        self.assertEqual(app.SUPPLIER_SPEC.key, "suppliers")
        self.assertEqual(app.SUPPLIER_SPEC.fields[2].key, "city_id")
        self.assertEqual(app.SUPPLIER_SPEC.fields[2].editor, "lookup")

    def test_all_required_editor_and_data_types_are_present(self):
        editors = {field.editor for spec in app.DICTIONARIES for field in spec.fields}
        data_types = {column.data_type for spec in app.DICTIONARIES for column in spec.columns}
        for required_editor in ("text", "multiline", "lookup", "date", "int", "decimal"):
            self.assertIn(required_editor, editors)
        for required_type in ("text", "multiline", "date", "int", "decimal"):
            self.assertIn(required_type, data_types)

    def test_display_columns_do_not_expose_primary_or_foreign_keys(self):
        for spec in app.DICTIONARIES:
            with self.subTest(spec=spec.key):
                display_columns = [column.key for column in spec.columns]
                self.assertNotIn(spec.pk, display_columns)
                self.assertFalse(any(column == "id" or column.endswith("_id") for column in display_columns))

    def test_sqlite_schema_has_required_foreign_key(self):
        foreign_keys = self.conn.execute("PRAGMA foreign_key_list(suppliers)").fetchall()
        self.assertTrue(
            any(row[2] == "cities" and row[3] == "city_id" and row[4] == "city_id" for row in foreign_keys)
        )

    def test_connect_db_enables_foreign_keys(self):
        self.assertEqual(self.conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_schema_has_history_tables(self):
        tables = {
            row[0]
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        for table in ("city_history", "supplier_history"):
            self.assertIn(table, tables)

    def test_initialize_database_is_idempotent(self):
        for _ in range(5):
            app.initialize_database()
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM cities").fetchone()[0], 3)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0], 3)

    def test_seed_repairs_partially_missing_supplier_examples(self):
        self.conn.execute("DELETE FROM suppliers WHERE name = ?", ("Brest Marine Systems",))
        self.conn.commit()
        app.initialize_database()
        names = [row[0] for row in self.conn.execute("SELECT name FROM suppliers ORDER BY name")]
        self.assertIn("Brest Marine Systems", names)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0], 3)

    def test_invalid_foreign_key_insert_is_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.harness.save_record(app.SUPPLIER_SPEC, self.supplier_values(city_id=999999), None)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0], 3)

    def test_save_record_rejects_unexpected_field_names(self):
        with self.assertRaises(ValueError):
            self.harness.save_record(app.CITY_SPEC, {"name": "X", "city_id": 1}, None)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM cities").fetchone()[0], 3)

    def test_zero_boundary_values_are_accepted(self):
        self.harness.save_record(
            app.CITY_SPEC,
            self.city_values("zero", population=0, area_km2="0.00"),
            None,
        )
        row = self.conn.execute("SELECT population, area_km2 FROM cities WHERE name = ?", ("City zero",)).fetchone()
        self.assertEqual(row["population"], 0)
        self.assertEqual(float(row["area_km2"]), 0.0)

    def test_database_constraints_reject_negative_numbers(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.harness.save_record(app.CITY_SPEC, self.city_values("badpop", population=-1), None)
        with self.assertRaises(sqlite3.IntegrityError):
            self.harness.save_record(app.SUPPLIER_SPEC, self.supplier_values(suffix="bademp", employees_count=-1), None)

    def test_large_valid_numeric_values_survive_round_trip(self):
        self.harness.save_record(
            app.SUPPLIER_SPEC,
            self.supplier_values(suffix="large", employees_count=999999, annual_budget="999999999999.99"),
            None,
        )
        row = self.conn.execute("SELECT employees_count, annual_budget FROM suppliers WHERE inn = ?", ("INNlarge",)).fetchone()
        self.assertEqual(row["employees_count"], 999999)
        self.assertEqual(str(row["annual_budget"]), "999999999999.99")

    def test_soft_deleted_rows_are_hidden_from_fetch_rows(self):
        city_id = self.conn.execute("SELECT city_id FROM cities LIMIT 1").fetchone()[0]
        self.conn.execute("UPDATE cities SET is_deleted = 1 WHERE city_id = ?", (city_id,))
        self.conn.commit()
        rows = self.harness.fetch_rows(app.CITY_SPEC)
        self.assertEqual(len(rows), 2)
        self.assertNotIn(city_id, [row["city_id"] for row in rows])

    def test_archived_selected_city_stays_available_in_lookup(self):
        city_id = self.conn.execute("SELECT city_id FROM cities LIMIT 1").fetchone()[0]
        self.conn.execute("UPDATE cities SET is_deleted = 1 WHERE city_id = ?", (city_id,))
        self.conn.commit()
        labels_without_selection, ids_without_selection, _ = self.harness.city_options(None)
        labels_with_selection, ids_with_selection, selected_index = self.harness.city_options(city_id)
        self.assertNotIn(city_id, ids_without_selection)
        self.assertIn(city_id, ids_with_selection)
        self.assertIsNotNone(selected_index)
        self.assertIn("архив", labels_with_selection[selected_index])
        self.assertTrue(all("архив" not in label for label in labels_without_selection))

    def test_city_label_by_id_handles_missing_and_archived_city(self):
        self.harness.city_label_by_id = app.ReferenceApp.city_label_by_id.__get__(self.harness, AppHarness)
        self.assertEqual(self.harness.city_label_by_id(None), "Не указан")
        self.assertEqual(self.harness.city_label_by_id(999999), "Не указан")
        city_id = self.conn.execute("SELECT city_id FROM cities LIMIT 1").fetchone()[0]
        self.conn.execute("UPDATE cities SET is_deleted = 1 WHERE city_id = ?", (city_id,))
        self.conn.commit()
        self.assertIn("архив", self.harness.city_label_by_id(city_id))

    def test_descending_sorting_toggles_order_correctly(self):
        rows = self.harness.fetch_rows(app.CITY_SPEC)
        ascending = self.harness.sorted_rows(rows, "population", False)
        descending = self.harness.sorted_rows(rows, "population", True)
        self.assertEqual([row["city_id"] for row in descending], list(reversed([row["city_id"] for row in ascending])))

    def test_formatters_handle_empty_and_invalid_values(self):
        self.assertEqual(app.format_date(None), "")
        self.assertEqual(app.format_date(""), "")
        self.assertEqual(app.format_date("not-a-date"), "not-a-date")
        self.assertEqual(app.format_decimal(None), "")
        self.assertEqual(app.format_decimal(""), "")
        self.assertEqual(app.format_decimal("not-a-number"), "not-a-number")

    def test_compact_text_removes_extra_whitespace_and_truncates(self):
        self.assertEqual(app.compact_text(" one\n two\tthree "), "one two three")
        compacted = app.compact_text("x" * 100, limit=10)
        self.assertEqual(len(compacted), 10)
        self.assertTrue(compacted.endswith("…"))

    def test_delete_supplier_soft_deletes_only_supplier(self):
        supplier_id = self.conn.execute("SELECT supplier_id FROM suppliers LIMIT 1").fetchone()[0]
        city_count_before = self.conn.execute("SELECT COUNT(*) FROM cities WHERE is_deleted = 0").fetchone()[0]
        self.harness.add_history(app.SUPPLIER_SPEC, "DELETE", supplier_id)
        self.conn.execute("UPDATE suppliers SET is_deleted = 1 WHERE supplier_id = ?", (supplier_id,))
        self.conn.commit()
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM cities WHERE is_deleted = 0").fetchone()[0], city_count_before)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM supplier_history WHERE supplier_id = ?", (supplier_id,)).fetchone()[0], 1)

    def test_reconnect_after_multiple_closed_connections(self):
        for _ in range(3):
            self.conn.close()
            rows = self.harness.fetch_rows(app.CITY_SPEC)
            self.conn = self.harness.conn
            self.assertEqual(len(rows), 3)

    def test_database_lock_error_rolls_back_pending_history(self):
        lock_conn = app.connect_db()
        city_id = self.conn.execute("SELECT city_id FROM cities WHERE is_deleted = 0 LIMIT 1").fetchone()[0]
        try:
            self.conn.execute("PRAGMA busy_timeout = 50")
            lock_conn.execute("BEGIN EXCLUSIVE")
            with self.assertRaises(sqlite3.OperationalError):
                self.harness.save_record(app.CITY_SPEC, self.city_values("locked"), city_id)
        finally:
            lock_conn.rollback()
            lock_conn.close()
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM city_history WHERE city_id = ?", (city_id,)).fetchone()[0],
            0,
        )

    def test_lookup_handles_exact_duplicate_display_labels_by_position(self):
        first = self.city_values("dup", name="Twin", country="Same")
        second = self.city_values("dup2", name="Twin", country="Same", population=2)
        self.harness.save_record(app.CITY_SPEC, first, None)
        self.harness.save_record(app.CITY_SPEC, second, None)

        labels, ids, _selected_index = self.harness.city_options()
        twin_pairs = [(label, city_id) for label, city_id in zip(labels, ids) if label == "Twin, Same"]

        self.assertEqual(len(twin_pairs), 2)
        self.assertNotEqual(twin_pairs[0][1], twin_pairs[1][1])

    def test_save_record_with_missing_required_columns_rolls_back_cleanly(self):
        before = self.conn.execute("SELECT COUNT(*) FROM cities").fetchone()[0]
        with self.assertRaises(sqlite3.IntegrityError):
            self.harness.save_record(app.CITY_SPEC, {"name": "Incomplete"}, None)
        after = self.conn.execute("SELECT COUNT(*) FROM cities").fetchone()[0]
        self.assertEqual(after, before)

    def test_write_after_closed_connection_reconnects_and_commits(self):
        self.conn.close()
        self.harness.save_record(app.CITY_SPEC, self.city_values("after-close"), None)
        self.conn = self.harness.conn
        row = self.conn.execute("SELECT name FROM cities WHERE name = ?", ("City after-close",)).fetchone()
        self.assertIsNotNone(row)

    def test_bulk_crud_stress_preserves_integrity_and_history(self):
        base_city_count = self.conn.execute("SELECT COUNT(*) FROM cities WHERE is_deleted = 0").fetchone()[0]
        base_supplier_count = self.conn.execute("SELECT COUNT(*) FROM suppliers WHERE is_deleted = 0").fetchone()[0]

        city_ids = []
        for index in range(40):
            self.harness.save_record(
                app.CITY_SPEC,
                self.city_values(
                    f"bulk-{index}",
                    foundation_date=f"20{index % 20:02d}-01-01",
                    population=index,
                    area_km2=f"{index + 1}.25",
                ),
                None,
            )
            city_ids.append(
                self.conn.execute("SELECT city_id FROM cities WHERE name = ?", (f"City bulk-{index}",)).fetchone()[0]
            )

        for index, city_id in enumerate(city_ids):
            self.harness.save_record(
                app.SUPPLIER_SPEC,
                self.supplier_values(city_id=city_id, suffix=f"bulk-{index}", employees_count=index),
                None,
            )

        for index, city_id in enumerate(city_ids[:20]):
            self.harness.save_record(
                app.CITY_SPEC,
                self.city_values(f"bulk-{index}", population=1000 + index),
                city_id,
            )

        for city_id in city_ids[::5]:
            self.harness.add_history(app.CITY_SPEC, "DELETE", city_id)
            self.conn.execute("UPDATE cities SET is_deleted = 1 WHERE city_id = ?", (city_id,))
        self.conn.commit()

        active_cities = self.conn.execute("SELECT COUNT(*) FROM cities WHERE is_deleted = 0").fetchone()[0]
        active_suppliers = self.conn.execute("SELECT COUNT(*) FROM suppliers WHERE is_deleted = 0").fetchone()[0]
        city_history = self.conn.execute("SELECT COUNT(*) FROM city_history").fetchone()[0]

        self.assertEqual(active_cities, base_city_count + 32)
        self.assertEqual(active_suppliers, base_supplier_count + 40)
        self.assertEqual(city_history, 28)

    def test_bulk_sorting_stress_for_numeric_decimal_and_dates(self):
        for index, population in enumerate((50, 0, 999, 10, 10, 5000, 1)):
            self.harness.save_record(
                app.CITY_SPEC,
                self.city_values(
                    f"sort-{index}",
                    foundation_date=f"2024-01-{index + 1:02d}",
                    population=population,
                    area_km2=f"{999 - population / 10:.2f}",
                ),
                None,
            )
        rows = self.harness.fetch_rows(app.CITY_SPEC)
        populations = [row["population"] for row in self.harness.sorted_rows(rows, "population", False)]
        dates = [row["foundation_date"] for row in self.harness.sorted_rows(rows, "foundation_date", False)]
        areas = [float(row["area_km2"]) for row in self.harness.sorted_rows(rows, "area_km2", False)]

        self.assertEqual(populations, sorted(populations))
        self.assertEqual(dates, sorted(dates))
        self.assertEqual(areas, sorted(areas))


class PartialSeedTests(unittest.TestCase):
    def test_partial_database_gets_missing_sample_suppliers(self):
        with TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            original_db_path = app.DB_PATH
            original_schema_path = app.SCHEMA_PATH
            app.DB_PATH = Path(temp_dir) / "partial.sqlite3"
            app.SCHEMA_PATH = Path("schema.sql")
            conn = app.connect_db()
            try:
                conn.executescript(Path("schema.sql").read_text(encoding="utf-8"))
                conn.execute(
                    """
                    INSERT INTO cities (name, country, foundation_date, population, area_km2, description)
                    VALUES ('One', 'X', '2024-01-01', 1, '1.00', 'x')
                    """
                )
                conn.commit()
                conn.close()

                app.initialize_database()
                conn = app.connect_db()
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0], 3)
            finally:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
                app.DB_PATH = original_db_path
                app.SCHEMA_PATH = original_schema_path


class GuiSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory(ignore_cleanup_errors=True)
        self.original_db_path = app.DB_PATH
        self.original_schema_path = app.SCHEMA_PATH
        app.DB_PATH = Path(self.temp_dir.name) / "gui.sqlite3"
        app.SCHEMA_PATH = Path("schema.sql")
        self.window = app.ReferenceApp()
        self.window.withdraw()
        self.window.update_idletasks()

    def tearDown(self):
        try:
            self.window.on_close()
        except Exception:
            pass
        app.DB_PATH = self.original_db_path
        app.SCHEMA_PATH = self.original_schema_path
        self.temp_dir.cleanup()

    def widget_texts(self, widget):
        texts = []
        try:
            text = widget.cget("text")
        except Exception:
            text = ""
        if text:
            texts.append(str(text))
        for child in widget.winfo_children():
            texts.extend(self.widget_texts(child))
        return texts

    def test_main_window_contains_student_info_and_dictionary_selector(self):
        visible_text = "\n".join(self.widget_texts(self.window))
        for expected in (
            app.STUDENT_FULL_NAME,
            app.STUDENT_COURSE,
            app.STUDENT_GROUP,
            app.STUDENT_YEAR,
            app.STUDENT_CITY,
        ):
            self.assertIn(expected, visible_text)

        self.assertEqual(tuple(self.window.dictionary_combo["values"]), tuple(spec.title for spec in app.DICTIONARIES))

    def test_tables_do_not_expose_internal_ids_and_switch_dictionary(self):
        self.window.select_dictionary(app.CITY_SPEC)
        city_columns = tuple(self.window.tree["columns"])
        self.assertEqual(city_columns, tuple(column.key for column in app.CITY_SPEC.columns))
        self.assertFalse(any(column.endswith("_id") or column == "id" for column in city_columns))
        self.assertEqual(len(self.window.tree.get_children()), 3)

        self.window.dictionary_combo.current(1)
        self.window.on_dictionary_changed()
        supplier_columns = tuple(self.window.tree["columns"])
        self.assertEqual(self.window.current_spec, app.SUPPLIER_SPEC)
        self.assertEqual(supplier_columns, tuple(column.key for column in app.SUPPLIER_SPEC.columns))
        self.assertFalse(any(column.endswith("_id") or column == "id" for column in supplier_columns))
        self.assertEqual(len(self.window.tree.get_children()), 3)

    def test_action_buttons_disabled_without_selection(self):
        self.window.tree.selection_remove(self.window.tree.selection())
        self.window.update_action_state()
        for button in (self.window.edit_button, self.window.view_button, self.window.delete_button, self.window.history_button):
            self.assertEqual(str(button["state"]), "disabled")

    def test_action_buttons_enabled_after_row_selection(self):
        first_row = self.window.tree.get_children()[0]
        self.window.tree.selection_set(first_row)
        self.window.update_action_state()
        for button in (self.window.edit_button, self.window.view_button, self.window.delete_button, self.window.history_button):
            self.assertEqual(str(button["state"]), "normal")

    def test_selected_record_id_tracks_tree_selection(self):
        self.assertIsNone(self.window.selected_record_id())
        first_row = self.window.tree.get_children()[0]
        self.window.tree.selection_set(first_row)
        self.assertEqual(self.window.selected_record_id(), int(first_row))

    def test_sort_by_column_toggles_ascending_and_descending(self):
        self.window.select_dictionary(app.CITY_SPEC)
        self.window.sort_by_column("population")
        ascending = [row["population"] for row in self.window.current_rows]
        self.window.sort_by_column("population")
        descending = [row["population"] for row in self.window.current_rows]
        self.assertEqual(ascending, sorted(ascending))
        self.assertEqual(descending, sorted(descending, reverse=True))

    def test_delete_cancel_leaves_record_active(self):
        self.window.select_dictionary(app.CITY_SPEC)
        record_id = int(self.window.tree.get_children()[0])
        self.window.tree.selection_set(str(record_id))
        with mock.patch.object(app.messagebox, "askyesno", return_value=False):
            self.window.delete_record()
        is_deleted = self.window.conn.execute(
            "SELECT is_deleted FROM cities WHERE city_id = ?",
            (record_id,),
        ).fetchone()[0]
        self.assertEqual(is_deleted, 0)

    def test_refresh_recovers_after_connection_close(self):
        self.window.conn.close()
        self.window.refresh_rows()
        self.assertEqual(len(self.window.current_rows), 3)
        self.assertEqual(len(self.window.tree.get_children()), 3)

    def test_status_text_updates_after_dictionary_switch(self):
        self.window.select_dictionary(app.SUPPLIER_SPEC)
        self.assertIn(app.SUPPLIER_SPEC.title, self.window.status.get())
        self.assertIn("3", self.window.status.get())

    def test_history_dialog_renders_saved_history(self):
        city_values = {
            "name": "History City",
            "country": "Country",
            "foundation_date": "2020-01-01",
            "population": 10,
            "area_km2": "1.00",
            "description": "Before",
        }
        self.window.save_record(app.CITY_SPEC, city_values, None)
        city_id = self.window.conn.execute("SELECT city_id FROM cities WHERE name = ?", ("History City",)).fetchone()[0]
        city_values["description"] = "After"
        self.window.save_record(app.CITY_SPEC, city_values, city_id)
        dialog = app.HistoryDialog(self.window, app.CITY_SPEC, city_id)
        dialog.withdraw()
        try:
            self.assertEqual(len(dialog.tree.get_children()), 1)
        finally:
            dialog.destroy()

    def test_calendar_popup_pick_returns_iso_date_and_closes(self):
        selected = []
        popup = app.CalendarPopup(self.window, date(2024, 2, 1), selected.append)
        popup.withdraw()
        popup.pick(29)
        self.assertEqual(selected, ["2024-02-29"])
        self.assertFalse(popup.winfo_exists())

    def test_calendar_popup_navigation_crosses_year_boundaries(self):
        popup = app.CalendarPopup(self.window, date(2024, 1, 1), lambda _value: None)
        popup.withdraw()
        try:
            popup.prev_month()
            self.assertEqual((popup.year, popup.month), (2023, 12))
            popup.next_month()
            self.assertEqual((popup.year, popup.month), (2024, 1))
        finally:
            if popup.winfo_exists():
                popup.destroy()

    def test_gui_save_edit_history_and_delete_keep_dependencies(self):
        city_values = {
            "name": "Тестовый город",
            "country": "Беларусь",
            "foundation_date": "2020-01-02",
            "population": 12345,
            "area_km2": "67.89",
            "description": "Город для автоматической проверки.",
        }
        self.window.save_record(app.CITY_SPEC, city_values, None)
        new_city_id = self.window.conn.execute(
            "SELECT city_id FROM cities WHERE name = ?",
            (city_values["name"],),
        ).fetchone()[0]

        city_values["population"] = 54321
        self.window.save_record(app.CITY_SPEC, city_values, new_city_id)
        history = self.window.get_history(app.CITY_SPEC, new_city_id)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["population"], 12345)

        linked_city_id = self.window.conn.execute(
            "SELECT city_id FROM suppliers WHERE is_deleted = 0 LIMIT 1"
        ).fetchone()[0]
        suppliers_before = self.window.conn.execute(
            "SELECT COUNT(*) FROM suppliers WHERE is_deleted = 0"
        ).fetchone()[0]

        self.window.select_dictionary(app.CITY_SPEC)
        self.window.tree.selection_set(str(linked_city_id))
        with mock.patch.object(app.messagebox, "askyesno", return_value=True):
            self.window.delete_record()

        suppliers_after = self.window.conn.execute(
            "SELECT COUNT(*) FROM suppliers WHERE is_deleted = 0"
        ).fetchone()[0]
        deleted_city = self.window.conn.execute(
            "SELECT is_deleted FROM cities WHERE city_id = ?",
            (linked_city_id,),
        ).fetchone()[0]
        self.assertEqual(suppliers_after, suppliers_before)
        self.assertEqual(deleted_city, 1)

    def test_record_dialog_collects_lookup_id_for_duplicate_city_names(self):
        self.window.select_dictionary(app.SUPPLIER_SPEC)
        dialog = object.__new__(app.RecordDialog)
        dialog.spec = app.SUPPLIER_SPEC
        dialog.widgets = {}
        dialog.lookup_ids = {}
        labels, city_ids, _selected_index = self.window.city_options()
        widgets = []
        try:
            for field in app.SUPPLIER_SPEC.fields:
                if field.editor == "lookup":
                    widget = app.ttk.Combobox(self.window, state="readonly", values=labels)
                    widget.current(0)
                    dialog.lookup_ids[field.key] = city_ids
                elif field.editor == "multiline":
                    widget = app.tk.Text(self.window)
                else:
                    widget = app.ttk.Entry(self.window)
                dialog.widgets[field.key] = widget
                widgets.append(widget)

            duplicate_name_count = self.window.conn.execute(
                "SELECT COUNT(*) FROM (SELECT name FROM cities GROUP BY name HAVING COUNT(*) > 1)"
            ).fetchone()[0]

            self.assertGreaterEqual(duplicate_name_count, 1)
            self.assertEqual(len(city_ids), len(set(city_ids)))

            selected_city_id = city_ids[0]
            for key, value in {
                "name": "Проверочный поставщик",
                "inn": "123TEST",
                "contract_date": "01.05.2026",
                "employees_count": "7",
                "annual_budget": "1234,56",
                "address": "Первая строка\nВторая строка",
                "comment": "Комментарий",
            }.items():
                widget = dialog.widgets[key]
                if isinstance(widget, app.tk.Text):
                    widget.delete("1.0", "end")
                    widget.insert("1.0", value)
                else:
                    widget.delete(0, "end")
                    widget.insert(0, value)

            values = dialog.collect_values()
            self.assertEqual(values["city_id"], selected_city_id)
            self.assertEqual(values["contract_date"], "2026-05-01")
            self.assertEqual(values["annual_budget"], "1234.56")
        finally:
            for widget in widgets:
                widget.destroy()


if __name__ == "__main__":
    unittest.main()
