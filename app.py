from __future__ import annotations

import calendar
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path


def configure_tcl_tk_paths() -> None:
    """Help Tkinter find Tcl/Tk files in portable or repaired Python installs."""
    tcl_root = Path(sys.base_prefix) / "tcl"
    tcl_library = tcl_root / "tcl8.6"
    tk_library = tcl_root / "tk8.6"
    if tcl_library.exists():
        os.environ.setdefault("TCL_LIBRARY", str(tcl_library))
    if tk_library.exists():
        os.environ.setdefault("TK_LIBRARY", str(tk_library))


configure_tcl_tk_paths()

from tkinter import messagebox
import tkinter as tk
from tkinter import ttk


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "reference_module.sqlite3"
SCHEMA_PATH = BASE_DIR / "schema.sql"

STUDENT_FULL_NAME = "Наркевич Кирилл Павлович"
STUDENT_COURSE = "3 курс"
STUDENT_GROUP = "2 группа"
STUDENT_YEAR = "2026"
STUDENT_CITY = "Минск"


@dataclass(frozen=True)
class ColumnSpec:
    key: str
    title: str
    data_type: str
    width: int = 140
    anchor: str = "w"


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    editor: str
    required: bool = True
    min_value: Decimal | int | None = None


@dataclass(frozen=True)
class DictionarySpec:
    key: str
    title: str
    table: str
    pk: str
    history_table: str
    columns: tuple[ColumnSpec, ...]
    fields: tuple[FieldSpec, ...]


CITY_SPEC = DictionarySpec(
    key="cities",
    title="Города",
    table="cities",
    pk="city_id",
    history_table="city_history",
    columns=(
        ColumnSpec("name", "Город", "text", 150),
        ColumnSpec("country", "Страна", "text", 140),
        ColumnSpec("foundation_date", "Дата основания", "date", 125, "center"),
        ColumnSpec("population", "Население", "int", 115, "e"),
        ColumnSpec("area_km2", "Площадь, км²", "decimal", 115, "e"),
        ColumnSpec("description", "Описание", "multiline", 320),
    ),
    fields=(
        FieldSpec("name", "Название города", "text"),
        FieldSpec("country", "Страна", "text"),
        FieldSpec("foundation_date", "Дата основания", "date"),
        FieldSpec("population", "Население", "int", min_value=0),
        FieldSpec("area_km2", "Площадь, км²", "decimal", min_value=Decimal("0")),
        FieldSpec("description", "Описание", "multiline"),
    ),
)

SUPPLIER_SPEC = DictionarySpec(
    key="suppliers",
    title="Поставщики оборудования",
    table="suppliers",
    pk="supplier_id",
    history_table="supplier_history",
    columns=(
        ColumnSpec("name", "Поставщик", "text", 190),
        ColumnSpec("inn", "УНП/ИНН", "text", 110),
        ColumnSpec("city_label", "Город", "text", 165),
        ColumnSpec("contract_date", "Дата договора", "date", 120, "center"),
        ColumnSpec("employees_count", "Сотрудники", "int", 100, "e"),
        ColumnSpec("annual_budget", "Бюджет, BYN", "decimal", 120, "e"),
        ColumnSpec("address", "Адрес", "multiline", 240),
        ColumnSpec("comment", "Комментарий", "multiline", 260),
    ),
    fields=(
        FieldSpec("name", "Название поставщика", "text"),
        FieldSpec("inn", "УНП/ИНН", "text"),
        FieldSpec("city_id", "Город", "lookup"),
        FieldSpec("contract_date", "Дата договора", "date"),
        FieldSpec("employees_count", "Количество сотрудников", "int", min_value=0),
        FieldSpec("annual_budget", "Годовой бюджет, BYN", "decimal", min_value=Decimal("0")),
        FieldSpec("address", "Юридический адрес", "multiline"),
        FieldSpec("comment", "Комментарий", "multiline"),
    ),
)

DICTIONARIES = (CITY_SPEC, SUPPLIER_SPEC)


def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_database() -> None:
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Не найден файл схемы: {SCHEMA_PATH}")

    conn = connect_db()
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        seed_database(conn)
        conn.commit()
    finally:
        conn.close()


def seed_database(conn: sqlite3.Connection) -> None:
    city_ids: dict[tuple[str, str], int] = {}
    city_rows = [
        (
            "Брест",
            "Беларусь",
            "1019-01-01",
            339700,
            "146.12",
            "Областной центр на западе Беларуси. В справочнике оставлен как пример города с повторяющимся названием.",
        ),
        (
            "Брест",
            "Франция",
            "1631-01-01",
            139456,
            "49.51",
            "Портовый город во Франции. Совпадение названия проверяет корректную работу выпадающего списка по внутреннему id.",
        ),
        (
            "Минск",
            "Беларусь",
            "1067-01-01",
            1992862,
            "348.84",
            "Столица Беларуси и крупный деловой центр.",
        ),
    ]

    for row in city_rows:
        existing = conn.execute(
            "SELECT city_id FROM cities WHERE name = ? AND country = ? ORDER BY city_id LIMIT 1",
            (row[0], row[1]),
        ).fetchone()
        if existing is None:
            cursor = conn.execute(
                """
                INSERT INTO cities (name, country, foundation_date, population, area_km2, description)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                row,
            )
            city_ids[(row[0], row[1])] = int(cursor.lastrowid)
        else:
            city_ids[(row[0], row[1])] = int(existing["city_id"])

    supplier_rows = [
        (
            city_ids[("Минск", "Беларусь")],
            "БелТехСнаб",
            "190123456",
            "2024-09-12",
            42,
            "185000.50",
            "г. Минск, ул. Инженерная, 10",
            "Поставляет учебные стенды и измерительное оборудование.",
        ),
        (
            city_ids[("Брест", "Беларусь")],
            "ЛабКомплект",
            "291987654",
            "2025-02-03",
            18,
            "73500.00",
            "г. Брест, ул. Московская, 18",
            "Основной поставщик расходных материалов для лабораторий.",
        ),
        (
            city_ids[("Брест", "Франция")],
            "Brest Marine Systems",
            "FR778812",
            "2023-11-21",
            63,
            "252300.75",
            "29200 Brest, Rue Jean Jaurès, 6",
            "Пример иностранного поставщика с тем же названием города в выпадающем списке.",
        ),
    ]

    for row in supplier_rows:
        existing = conn.execute(
            "SELECT supplier_id FROM suppliers WHERE name = ? AND inn = ? ORDER BY supplier_id LIMIT 1",
            (row[1], row[2]),
        ).fetchone()
        if existing is not None:
            continue
        conn.execute(
            """
            INSERT INTO suppliers
                (city_id, name, inn, contract_date, employees_count, annual_budget, address, comment)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )


def current_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_date_input(raw_value: str) -> str:
    value = raw_value.strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError("Введите дату в формате ДД.ММ.ГГГГ.")


def format_date(raw_value: object) -> str:
    if raw_value in (None, ""):
        return ""
    try:
        return datetime.strptime(str(raw_value), "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return str(raw_value)


def parse_decimal_input(raw_value: str) -> str:
    value = raw_value.strip().replace(",", ".")
    try:
        parsed = Decimal(value)
        if not parsed.is_finite():
            raise InvalidOperation
        parsed = parsed.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise ValueError("Введите число с фиксированной запятой, например 1250,50.")
    return f"{parsed:.2f}"


def format_decimal(raw_value: object) -> str:
    if raw_value in (None, ""):
        return ""
    try:
        return f"{Decimal(str(raw_value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"
    except InvalidOperation:
        return str(raw_value)


def compact_text(raw_value: object, limit: int = 90) -> str:
    value = " ".join(str(raw_value or "").split())
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


def city_label(row: sqlite3.Row) -> str:
    suffix = " (архив)" if row["is_deleted"] else ""
    return f"{row['name']}, {row['country']}{suffix}"


class CalendarPopup(tk.Toplevel):
    def __init__(self, parent: tk.Widget, initial_date: date, on_select):
        super().__init__(parent)
        self.title("Выбор даты")
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.on_select = on_select
        self.year = initial_date.year
        self.month = initial_date.month
        self.selected_date = initial_date

        self.header = ttk.Frame(self, padding=(10, 10, 10, 4))
        self.header.grid(row=0, column=0, sticky="ew")
        self.body = ttk.Frame(self, padding=(10, 4, 10, 10))
        self.body.grid(row=1, column=0)

        ttk.Button(self.header, text="‹", width=3, command=self.prev_month).grid(row=0, column=0)
        self.title_label = ttk.Label(self.header, width=22, anchor="center")
        self.title_label.grid(row=0, column=1, padx=8)
        ttk.Button(self.header, text="›", width=3, command=self.next_month).grid(row=0, column=2)

        self.render()

    def prev_month(self) -> None:
        if self.month == 1:
            self.month = 12
            self.year -= 1
        else:
            self.month -= 1
        self.render()

    def next_month(self) -> None:
        if self.month == 12:
            self.month = 1
            self.year += 1
        else:
            self.month += 1
        self.render()

    def render(self) -> None:
        for child in self.body.winfo_children():
            child.destroy()

        month_names = (
            "",
            "Январь",
            "Февраль",
            "Март",
            "Апрель",
            "Май",
            "Июнь",
            "Июль",
            "Август",
            "Сентябрь",
            "Октябрь",
            "Ноябрь",
            "Декабрь",
        )
        self.title_label.config(text=f"{month_names[self.month]} {self.year}")

        for column, name in enumerate(("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")):
            ttk.Label(self.body, text=name, width=4, anchor="center").grid(row=0, column=column, pady=(0, 4))

        weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(self.year, self.month)
        for row_index, week in enumerate(weeks, start=1):
            for column, day_number in enumerate(week):
                if day_number == 0:
                    ttk.Label(self.body, text="", width=4).grid(row=row_index, column=column, padx=1, pady=1)
                    continue
                button = ttk.Button(
                    self.body,
                    text=str(day_number),
                    width=4,
                    command=lambda day=day_number: self.pick(day),
                )
                button.grid(row=row_index, column=column, padx=1, pady=1)

    def pick(self, day_number: int) -> None:
        selected = date(self.year, self.month, day_number)
        self.on_select(selected.isoformat())
        self.destroy()


class RecordDialog(tk.Toplevel):
    def __init__(self, parent: "ReferenceApp", spec: DictionarySpec, mode: str, record_id: int | None = None):
        super().__init__(parent)
        self.parent_app = parent
        self.spec = spec
        self.mode = mode
        self.record_id = record_id
        self.widgets: dict[str, tk.Widget] = {}
        self.lookup_ids: dict[str, list[int | None]] = {}
        self.title(self.dialog_title)
        self.resizable(False, True)
        self.transient(parent)
        self.grab_set()

        self.record = parent.get_record(spec, record_id) if record_id is not None else None

        self.container = ttk.Frame(self, padding=16)
        self.container.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.container.columnconfigure(1, weight=1)

        ttk.Label(self.container, text=spec.title, font=("Segoe UI", 13, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12)
        )

        self.build_fields()
        self.build_buttons()
        self.bind("<Escape>", lambda _event: self.destroy())
        self.wait_visibility()
        self.focus()

    @property
    def dialog_title(self) -> str:
        names = {"add": "Добавление", "edit": "Редактирование", "view": "Просмотр"}
        return f"{names[self.mode]}: {self.spec.title}"

    def build_fields(self) -> None:
        for row_index, field in enumerate(self.spec.fields, start=1):
            ttk.Label(self.container, text=field.label).grid(row=row_index, column=0, sticky="nw", padx=(0, 12), pady=5)
            value = self.record[field.key] if self.record is not None and field.key in self.record.keys() else ""

            if field.editor == "multiline":
                frame = ttk.Frame(self.container)
                frame.grid(row=row_index, column=1, sticky="ew", pady=5)
                text = tk.Text(frame, width=58, height=4, wrap="word", font=("Segoe UI", 10))
                text.grid(row=0, column=0, sticky="ew")
                scrollbar = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
                scrollbar.grid(row=0, column=1, sticky="ns")
                text.configure(yscrollcommand=scrollbar.set)
                text.insert("1.0", str(value or ""))
                self.widgets[field.key] = text
            elif field.editor == "date":
                frame = ttk.Frame(self.container)
                frame.grid(row=row_index, column=1, sticky="w", pady=5)
                entry = ttk.Entry(frame, width=18)
                entry.grid(row=0, column=0, sticky="w")
                entry.insert(0, format_date(value))
                calendar_button = ttk.Button(frame, text="Календарь", command=lambda key=field.key: self.open_calendar(key))
                calendar_button.grid(row=0, column=1, padx=(8, 0))
                if self.mode == "view":
                    calendar_button.configure(state="disabled")
                self.widgets[field.key] = entry
            elif field.editor == "lookup":
                combo = ttk.Combobox(self.container, state="readonly", width=55)
                combo.grid(row=row_index, column=1, sticky="ew", pady=5)
                selected_id = int(value) if value not in (None, "") else None
                labels, ids, selected_index = self.parent_app.city_options(selected_id)
                combo.configure(values=labels)
                if selected_index is not None:
                    combo.current(selected_index)
                self.lookup_ids[field.key] = ids
                self.widgets[field.key] = combo
            else:
                entry = ttk.Entry(self.container, width=58)
                entry.grid(row=row_index, column=1, sticky="ew", pady=5)
                if field.editor == "decimal":
                    entry.insert(0, format_decimal(value))
                else:
                    entry.insert(0, str(value or ""))
                self.widgets[field.key] = entry

            if self.mode == "view":
                self.disable_widget(self.widgets[field.key])

    def build_buttons(self) -> None:
        row = len(self.spec.fields) + 2
        button_frame = ttk.Frame(self.container)
        button_frame.grid(row=row, column=0, columnspan=2, sticky="e", pady=(12, 0))
        if self.mode != "view":
            ttk.Button(button_frame, text="Сохранить", command=self.save).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(button_frame, text="Закрыть", command=self.destroy).grid(row=0, column=1)

    def disable_widget(self, widget: tk.Widget) -> None:
        if isinstance(widget, tk.Text):
            widget.configure(state="disabled")
        elif isinstance(widget, ttk.Combobox):
            widget.configure(state="disabled")
        else:
            widget.configure(state="readonly")

    def open_calendar(self, field_key: str) -> None:
        widget = self.widgets[field_key]
        if not isinstance(widget, ttk.Entry):
            return
        try:
            initial = datetime.strptime(parse_date_input(widget.get()), "%Y-%m-%d").date()
        except ValueError:
            initial = date.today()

        def set_date(value: str) -> None:
            widget.delete(0, tk.END)
            widget.insert(0, format_date(value))

        CalendarPopup(self, initial, set_date)

    def save(self) -> None:
        try:
            values = self.collect_values()
        except ValueError as error:
            messagebox.showerror("Проверьте данные", str(error), parent=self)
            return

        try:
            self.parent_app.save_record(self.spec, values, self.record_id)
        except sqlite3.Error as error:
            messagebox.showerror("Ошибка базы данных", str(error), parent=self)
            return

        self.parent_app.refresh_rows()
        self.destroy()

    def collect_values(self) -> dict[str, object]:
        values: dict[str, object] = {}
        for field in self.spec.fields:
            widget = self.widgets[field.key]
            if isinstance(widget, tk.Text):
                raw_value = widget.get("1.0", "end-1c").strip()
            elif isinstance(widget, ttk.Combobox):
                index = widget.current()
                if index < 0:
                    raw_value = None
                else:
                    raw_value = self.lookup_ids[field.key][index]
            else:
                raw_value = widget.get().strip()

            if field.required and raw_value in (None, ""):
                raise ValueError(f"Поле «{field.label}» обязательно для заполнения.")

            if field.editor == "date":
                values[field.key] = parse_date_input(str(raw_value))
            elif field.editor == "int":
                try:
                    parsed = int(str(raw_value))
                except ValueError:
                    raise ValueError(f"Поле «{field.label}» должно быть целым числом.")
                if field.min_value is not None and parsed < int(field.min_value):
                    raise ValueError(f"Поле «{field.label}» не может быть меньше {field.min_value}.")
                values[field.key] = parsed
            elif field.editor == "decimal":
                parsed = parse_decimal_input(str(raw_value))
                if field.min_value is not None and Decimal(parsed) < Decimal(field.min_value):
                    raise ValueError(f"Поле «{field.label}» не может быть меньше {field.min_value}.")
                values[field.key] = parsed
            else:
                values[field.key] = raw_value
        return values


class HistoryDialog(tk.Toplevel):
    def __init__(self, parent: "ReferenceApp", spec: DictionarySpec, record_id: int):
        super().__init__(parent)
        self.parent_app = parent
        self.spec = spec
        self.record_id = record_id
        self.title(f"История: {spec.title}")
        self.geometry("980x420")
        self.transient(parent)

        container = ttk.Frame(self, padding=14)
        container.pack(fill="both", expand=True)

        ttk.Label(container, text=f"История изменений: {spec.title}", font=("Segoe UI", 12, "bold")).pack(anchor="w")

        columns = ("operation", "changed_at", *[column.key for column in spec.columns])
        self.tree = ttk.Treeview(container, columns=columns, show="headings", height=12)
        self.tree.pack(fill="both", expand=True, pady=(10, 0), side="left")

        y_scroll = ttk.Scrollbar(container, orient="vertical", command=self.tree.yview)
        y_scroll.pack(side="right", fill="y", pady=(10, 0))
        self.tree.configure(yscrollcommand=y_scroll.set)

        headings = {"operation": "Операция", "changed_at": "Когда"}
        for column in spec.columns:
            headings[column.key] = column.title

        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=150, anchor="w", stretch=True)

        self.load_rows()

    def load_rows(self) -> None:
        rows = self.parent_app.get_history(self.spec, self.record_id)
        if not rows:
            self.tree.insert("", "end", values=("Истории пока нет", "", *["" for _ in self.spec.columns]))
            return

        for row in rows:
            values = [self.operation_label(row["operation"]), row["changed_at"]]
            for column in self.spec.columns:
                if column.key == "city_label":
                    values.append(self.parent_app.city_label_by_id(row["city_id"]))
                else:
                    values.append(self.parent_app.format_for_column(column, row[column.key]))
            self.tree.insert("", "end", values=values)

    @staticmethod
    def operation_label(operation: str) -> str:
        return {"UPDATE": "Редактирование", "DELETE": "Удаление"}.get(operation, operation)


class ReferenceApp(tk.Tk):
    def __init__(self):
        initialize_database()
        super().__init__()
        self.title("Модуль справочной информации")
        self.geometry("1180x720")
        self.minsize(980, 620)

        self.conn = connect_db()
        self.spec_by_title = {spec.title: spec for spec in DICTIONARIES}
        self.current_spec = DICTIONARIES[0]
        self.current_rows: list[sqlite3.Row] = []
        self.sort_column: str | None = None
        self.sort_descending = False

        self.configure_style()
        self.build_layout()
        self.select_dictionary(self.current_spec)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def ensure_connection(self) -> sqlite3.Connection:
        try:
            self.conn.execute("SELECT 1")
        except sqlite3.ProgrammingError:
            try:
                self.conn.close()
            except sqlite3.Error:
                pass
            self.conn = connect_db()
        return self.conn

    def rollback_safely(self) -> None:
        try:
            self.conn.rollback()
        except sqlite3.Error:
            pass

    def configure_style(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Treeview", rowheight=28, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Muted.TLabel", foreground="#555555")

    def build_layout(self) -> None:
        header = ttk.Frame(self, padding=(18, 16, 18, 10))
        header.pack(fill="x")

        ttk.Label(header, text="Модуль справочной информации бизнес-приложения", style="Header.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        info = f"{STUDENT_FULL_NAME}, {STUDENT_COURSE}, {STUDENT_GROUP}, {STUDENT_YEAR} год, {STUDENT_CITY}"
        ttk.Label(header, text=info, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))

        controls = ttk.Frame(self, padding=(18, 0, 18, 10))
        controls.pack(fill="x")
        ttk.Label(controls, text="Справочник").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.dictionary_combo = ttk.Combobox(
            controls,
            state="readonly",
            values=[spec.title for spec in DICTIONARIES],
            width=32,
        )
        self.dictionary_combo.current(0)
        self.dictionary_combo.grid(row=0, column=1, sticky="w", padx=(0, 14))
        self.dictionary_combo.bind("<<ComboboxSelected>>", self.on_dictionary_changed)

        self.add_button = ttk.Button(controls, text="Добавить", command=self.add_record)
        self.edit_button = ttk.Button(controls, text="Редактировать", command=self.edit_record)
        self.view_button = ttk.Button(controls, text="Просмотр", command=self.view_record)
        self.delete_button = ttk.Button(controls, text="Удалить", command=self.delete_record)
        self.history_button = ttk.Button(controls, text="История", command=self.view_history)
        self.refresh_button = ttk.Button(controls, text="Обновить", command=self.refresh_rows)

        for column, button in enumerate(
            (
                self.add_button,
                self.edit_button,
                self.view_button,
                self.delete_button,
                self.history_button,
                self.refresh_button,
            ),
            start=2,
        ):
            button.grid(row=0, column=column, padx=(0, 8))

        table_frame = ttk.Frame(self, padding=(18, 0, 18, 10))
        table_frame.pack(fill="both", expand=True)
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(table_frame, show="headings", selectmode="browse")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self.update_action_state())
        self.tree.bind("<Double-1>", lambda _event: self.view_record())

        y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.status = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.status, anchor="w", padding=(18, 8), style="Muted.TLabel").pack(fill="x")

    def on_dictionary_changed(self, _event=None) -> None:
        title = self.dictionary_combo.get()
        self.select_dictionary(self.spec_by_title[title])

    def select_dictionary(self, spec: DictionarySpec) -> None:
        self.current_spec = spec
        self.sort_column = None
        self.sort_descending = False
        self.configure_tree_columns()
        self.refresh_rows()

    def configure_tree_columns(self) -> None:
        self.tree.delete(*self.tree.get_children())
        columns = [column.key for column in self.current_spec.columns]
        self.tree.configure(columns=columns)
        for column in self.current_spec.columns:
            self.tree.heading(
                column.key,
                text=column.title,
                command=lambda key=column.key: self.sort_by_column(key),
            )
            self.tree.column(column.key, width=column.width, minwidth=80, anchor=column.anchor, stretch=True)

    def refresh_rows(self) -> None:
        try:
            self.current_rows = self.fetch_rows(self.current_spec)
        except sqlite3.Error as error:
            messagebox.showerror("Ошибка базы данных", str(error), parent=self)
            self.current_rows = []
        if self.sort_column:
            self.current_rows = self.sorted_rows(self.current_rows, self.sort_column, self.sort_descending)
        self.render_rows()
        self.update_action_state()
        self.status.set(f"Справочник «{self.current_spec.title}»: записей {len(self.current_rows)}")

    def fetch_rows(self, spec: DictionarySpec) -> list[sqlite3.Row]:
        conn = self.ensure_connection()
        if spec.key == "cities":
            query = """
                SELECT city_id, name, country, foundation_date, population, area_km2, description
                FROM cities
                WHERE is_deleted = 0
            """
        else:
            query = """
                SELECT
                    s.supplier_id,
                    s.name,
                    s.inn,
                    s.city_id,
                    COALESCE(c.name || ', ' || c.country ||
                        CASE WHEN c.is_deleted = 1 THEN ' (архив)' ELSE '' END, 'Не указан') AS city_label,
                    s.contract_date,
                    s.employees_count,
                    s.annual_budget,
                    s.address,
                    s.comment
                FROM suppliers AS s
                LEFT JOIN cities AS c ON c.city_id = s.city_id
                WHERE s.is_deleted = 0
            """
        return list(conn.execute(query))

    def render_rows(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for row in self.current_rows:
            values = []
            for column in self.current_spec.columns:
                values.append(self.format_for_column(column, row[column.key]))
            self.tree.insert("", "end", iid=str(row[self.current_spec.pk]), values=values)

    def sort_by_column(self, column_key: str) -> None:
        if self.sort_column == column_key:
            self.sort_descending = not self.sort_descending
        else:
            self.sort_column = column_key
            self.sort_descending = False
        self.current_rows = self.sorted_rows(self.current_rows, column_key, self.sort_descending)
        self.render_rows()

    def sorted_rows(self, rows: list[sqlite3.Row], column_key: str, descending: bool) -> list[sqlite3.Row]:
        column = next(column for column in self.current_spec.columns if column.key == column_key)

        def sort_key(row: sqlite3.Row):
            value = row[column.key]
            if value is None:
                return (1, "")
            if column.data_type == "int":
                return (0, int(value))
            if column.data_type == "decimal":
                return (0, Decimal(str(value)))
            if column.data_type == "date":
                return (0, datetime.strptime(str(value), "%Y-%m-%d").date())
            return (0, str(value).casefold())

        return sorted(rows, key=sort_key, reverse=descending)

    def format_for_column(self, column: ColumnSpec, value: object) -> str:
        if column.data_type == "date":
            return format_date(value)
        if column.data_type == "decimal":
            return format_decimal(value)
        if column.data_type == "multiline":
            return compact_text(value)
        return str(value or "")

    def selected_record_id(self) -> int | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return int(selection[0])

    def update_action_state(self) -> None:
        has_selection = self.selected_record_id() is not None
        state = "normal" if has_selection else "disabled"
        for button in (self.edit_button, self.view_button, self.delete_button, self.history_button):
            button.configure(state=state)

    def add_record(self) -> None:
        RecordDialog(self, self.current_spec, "add")

    def edit_record(self) -> None:
        record_id = self.selected_record_id()
        if record_id is not None:
            RecordDialog(self, self.current_spec, "edit", record_id)

    def view_record(self) -> None:
        record_id = self.selected_record_id()
        if record_id is not None:
            RecordDialog(self, self.current_spec, "view", record_id)

    def view_history(self) -> None:
        record_id = self.selected_record_id()
        if record_id is not None:
            HistoryDialog(self, self.current_spec, record_id)

    def delete_record(self) -> None:
        record_id = self.selected_record_id()
        if record_id is None:
            return

        extra = ""
        if self.current_spec.key == "cities":
            conn = self.ensure_connection()
            suppliers_count = conn.execute(
                "SELECT COUNT(*) FROM suppliers WHERE city_id = ? AND is_deleted = 0",
                (record_id,),
            ).fetchone()[0]
            if suppliers_count:
                extra = (
                    f"\n\nСвязанные поставщики сохранятся: {suppliers_count}. "
                    "Город будет помечен как архивный."
                )

        confirmed = messagebox.askyesno(
            "Подтверждение удаления",
            f"Удалить выбранную запись из справочника «{self.current_spec.title}»?{extra}",
            parent=self,
        )
        if not confirmed:
            return

        try:
            conn = self.ensure_connection()
            self.add_history(self.current_spec, "DELETE", record_id)
            conn.execute(
                f"UPDATE {self.current_spec.table} SET is_deleted = 1, updated_at = ? WHERE {self.current_spec.pk} = ?",
                (current_timestamp(), record_id),
            )
            conn.commit()
        except sqlite3.Error as error:
            self.rollback_safely()
            messagebox.showerror("Ошибка базы данных", str(error), parent=self)
            return
        self.refresh_rows()

    def get_record(self, spec: DictionarySpec, record_id: int | None) -> sqlite3.Row:
        if record_id is None:
            raise ValueError("record_id is required")
        query = f"SELECT * FROM {spec.table} WHERE {spec.pk} = ?"
        row = self.ensure_connection().execute(query, (record_id,)).fetchone()
        if row is None:
            raise ValueError("Запись не найдена")
        return row

    def validate_field_names(self, spec: DictionarySpec, field_names: list[str]) -> None:
        allowed_fields = {field.key for field in spec.fields}
        unexpected_fields = sorted(set(field_names) - allowed_fields)
        if unexpected_fields:
            raise ValueError(f"Недопустимые поля: {', '.join(unexpected_fields)}")

    def save_record(self, spec: DictionarySpec, values: dict[str, object], record_id: int | None) -> None:
        field_names = list(values.keys())
        self.validate_field_names(spec, field_names)
        conn = self.ensure_connection()
        try:
            if record_id is None:
                placeholders = ", ".join("?" for _ in field_names)
                columns = ", ".join(field_names)
                conn.execute(
                    f"INSERT INTO {spec.table} ({columns}) VALUES ({placeholders})",
                    tuple(values[name] for name in field_names),
                )
            else:
                self.add_history(spec, "UPDATE", record_id)
                assignments = ", ".join(f"{name} = ?" for name in field_names)
                conn.execute(
                    f"UPDATE {spec.table} SET {assignments}, updated_at = ? WHERE {spec.pk} = ?",
                    (*[values[name] for name in field_names], current_timestamp(), record_id),
                )
            conn.commit()
        except sqlite3.Error:
            self.rollback_safely()
            raise

    def add_history(self, spec: DictionarySpec, operation: str, record_id: int) -> None:
        if spec.key == "cities":
            snapshot_columns = (
                "city_id",
                "name",
                "country",
                "foundation_date",
                "population",
                "area_km2",
                "description",
                "is_deleted",
                "created_at",
                "updated_at",
            )
        else:
            snapshot_columns = (
                "supplier_id",
                "city_id",
                "name",
                "inn",
                "contract_date",
                "employees_count",
                "annual_budget",
                "address",
                "comment",
                "is_deleted",
                "created_at",
                "updated_at",
            )
        target_columns = ", ".join(("operation", "changed_at", *snapshot_columns))
        select_columns = ", ".join(snapshot_columns)
        self.ensure_connection().execute(
            f"""
            INSERT INTO {spec.history_table} ({target_columns})
            SELECT ?, ?, {select_columns}
            FROM {spec.table}
            WHERE {spec.pk} = ?
            """,
            (operation, current_timestamp(), record_id),
        )

    def get_history(self, spec: DictionarySpec, record_id: int) -> list[sqlite3.Row]:
        return list(
            self.ensure_connection().execute(
                f"SELECT * FROM {spec.history_table} WHERE {spec.pk} = ? ORDER BY changed_at DESC, history_id DESC",
                (record_id,),
            )
        )

    def city_options(self, selected_id: int | None = None) -> tuple[list[str], list[int | None], int | None]:
        conn = self.ensure_connection()
        if selected_id is None:
            rows = conn.execute(
                "SELECT city_id, name, country, is_deleted FROM cities WHERE is_deleted = 0 ORDER BY name, country"
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT city_id, name, country, is_deleted
                FROM cities
                WHERE is_deleted = 0 OR city_id = ?
                ORDER BY is_deleted, name, country
                """,
                (selected_id,),
            ).fetchall()

        labels = [city_label(row) for row in rows]
        ids = [int(row["city_id"]) for row in rows]
        selected_index = ids.index(selected_id) if selected_id in ids else None
        return labels, ids, selected_index

    def city_label_by_id(self, city_id: object) -> str:
        if city_id in (None, ""):
            return "Не указан"
        row = self.ensure_connection().execute(
            "SELECT city_id, name, country, is_deleted FROM cities WHERE city_id = ?",
            (city_id,),
        ).fetchone()
        return city_label(row) if row else "Не указан"

    def on_close(self) -> None:
        try:
            self.conn.close()
        except sqlite3.Error:
            pass
        self.destroy()


def main() -> None:
    if "--init-db" in sys.argv:
        initialize_database()
        print(f"База данных создана или обновлена: {DB_PATH}")
        return
    app = ReferenceApp()
    app.mainloop()


if __name__ == "__main__":
    main()
