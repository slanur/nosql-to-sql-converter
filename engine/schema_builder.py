from dataclasses import dataclass, field
from utils.type_mapper import get_sql_type, infer_dominant_type
from parser.flattener import flatten, extract_arrays

PRIMITIVE_COLUMN = "deger"  # ilkel dizi elemanlarının yazıldığı sütun


# Dizideki ilkel değerleri nesne gibi işlemek için tek sütunlu kayda çevirir
def as_record(item) -> dict:
    return item if isinstance(item, dict) else {PRIMITIVE_COLUMN: item}


@dataclass
class ParentRef:
    # Üst kaydın insert sırası, db_manager bunu gerçek id ile değiştirir
    index: int


@dataclass
class ColumnSchema:
   # Tek bir sütunu tanımlar
    name:        str
    sql_type:    str
    is_primary:  bool = False
    is_foreign:  bool = False
    foreign_ref: str  = ""  

    def to_sql(self) -> str:
        parts = [f'"{self.name}"', self.sql_type]

        if self.is_primary:
            parts.append("PRIMARY KEY AUTOINCREMENT")
        if self.is_foreign:
            pass
        if self.sql_type == "TEXT":
            parts.append("DEFAULT NULL")

        return " ".join(parts)


@dataclass
class TableSchema:
    #Tek bir SQL tablosunu tanımlar.
    name:        str
    columns:     list = field(default_factory=list)   
    foreign_keys: list = field(default_factory=list)  
    parent_table: str = ""  
    parent_key:   str = ""
    column_map:   dict = field(default_factory=dict)  # JSON alanı → sütun adı
    child_tables: dict = field(default_factory=dict)  # dizi adı → alt tablo adı

    def add_column(self, col: ColumnSchema):
        self.columns.append(col)

    def to_create_sql(self) -> str:
       
        lines = []
        for col in self.columns:
            lines.append(f"    {col.to_sql()}")

        for fk in self.foreign_keys:
            lines.append(f"    {fk}")

        body = ",\n".join(lines)
        return f'CREATE TABLE IF NOT EXISTS "{self.name}" (\n{body}\n);'


class SchemaBuilder:
 
    def __init__(self, separator: str = "_"):
        self.separator = separator
        self.schemas: list[TableSchema] = []
        self.table_names: set[str] = set()

    def build(self, data, root_table_name: str = "root") -> list[TableSchema]:

        self.schemas = []
        self.table_names = {root_table_name}

       
        if isinstance(data, list):
            records = data
        else:
            records = [data]

        self._process_table(
            records=records,
            table_name=root_table_name,
            parent_table="",
            parent_key=""
        )

        return self.schemas

    def _process_table(self,records: list,table_name: str,parent_table: str,parent_key: str):
        schema = TableSchema(name=table_name,parent_table=parent_table,parent_key=parent_key)

        pk_col = ColumnSchema(
            name="id",
            sql_type="INTEGER",
            is_primary=True
        )
        schema.add_column(pk_col)

        if parent_table and parent_key:
            fk_col_name = f"{parent_table}_id"
            fk_col = ColumnSchema(
                name=fk_col_name,
                sql_type="INTEGER",
                is_foreign=True,
                foreign_ref=f'"{parent_table}"("{parent_key}")'
            )
            schema.add_column(fk_col)
            schema.foreign_keys.append(
                f'FOREIGN KEY ("{fk_col_name}") REFERENCES "{parent_table}"("{parent_key}")'
            )

        column_values: dict[str, list] = {}  
        child_arrays: dict[str, list] = {}  

        for record in records:
            flat = flatten(as_record(record), separator=self.separator)
            primitives, arrays = extract_arrays(flat)

            for col_name, value in primitives.items():
                col_name_clean = self._sanitize_name(col_name)
                if col_name_clean not in column_values:
                    column_values[col_name_clean] = []
                column_values[col_name_clean].append(value)

            for arr_name, arr_value in arrays.items():
                arr_name_clean = self._sanitize_name(arr_name)
                if arr_name_clean not in child_arrays:
                    child_arrays[arr_name_clean] = []
                child_arrays[arr_name_clean].extend(arr_value)

        # id ve foreign key sütunlarıyla çakışan JSON alanları kaynak_ önekiyle korunur
        reserved = {col.name for col in schema.columns}
        taken = reserved | set(column_values)

        for col_name, values in column_values.items():
            final_name = col_name
            if col_name in reserved:
                final_name = self._unique_name(f"kaynak_{col_name}", taken)
                taken.add(final_name)

            schema.column_map[col_name] = final_name
            dominant_type = infer_dominant_type(values)
            col = ColumnSchema(name=final_name, sql_type=dominant_type)
            schema.add_column(col)

        self.schemas.append(schema)

        for arr_name, arr_records in child_arrays.items():
            # Aynı dizi adı başka yerde kullanıldıysa üst tablo adıyla ayrılır
            child_table = arr_name
            if child_table in self.table_names:
                child_table = self._unique_name(f"{table_name}_{arr_name}", self.table_names)

            self.table_names.add(child_table)
            schema.child_tables[arr_name] = child_table

            self._process_table(
                records=arr_records,
                table_name=child_table,
                parent_table=table_name,
                parent_key="id"
            )

    def _unique_name(self, name: str, taken: set) -> str:
        candidate = name
        suffix = 2
        while candidate in taken:
            candidate = f"{name}_{suffix}"
            suffix += 1
        return candidate

    def _sanitize_name(self, name: str) -> str:
       
        import re
        name = name.strip().lower()
        name = re.sub(r"[^\w]", "_", name)  
        name = re.sub(r"_+", "_", name)       
        name = name.strip("_")
        return name