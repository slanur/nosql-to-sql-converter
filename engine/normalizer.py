from parser.flattener import flatten, extract_arrays
from engine.schema_builder import ParentRef, TableSchema, as_record


class Normalizer:
 
    def __init__(self, schemas: list[TableSchema], separator: str = "_"):
        # Tablo adı → TableSchema eşlemesi
        self.schema_map: dict[str, TableSchema] = {s.name: s for s in schemas}
        self.separator = separator
        self.insert_ops: list[tuple[str, dict]] = [] 

    def generate_inserts(self, data, root_table_name: str) -> list[tuple[str, dict]]:
       
        self.insert_ops = [] # her çağrıda sıfırlanır oncekilerle karısmasın diye

        records = data if isinstance(data, list) else [data]

        for record in records:
            self._process_record(
                record=record,
                table_name=root_table_name,
                parent_id=None, #none cunku kokun ustunde kayıtlı id yok
                parent_table=""
            )

        return self.insert_ops

    def _process_record(self,record,table_name: str,parent_id,parent_table: str) -> int:

        schema = self.schema_map.get(table_name) #sema yoksa islem yapma
        if schema is None:
            return -1

        flat = flatten(as_record(record), separator=self.separator) # adress.city -> address_city olur
        primitives, arrays = extract_arrays(flat)

        #semadaki sütunlarla eşleştir
        schema_col_names = {col.name for col in schema.columns
                            if not col.is_primary}

        row_data = {}

        if parent_table and parent_id is not None:
            fk_col = f"{parent_table}_id"
            if fk_col in schema_col_names:
                row_data[fk_col] = ParentRef(parent_id)

        for raw_key, value in primitives.items():
            col_name = schema.column_map.get(self._sanitize_name(raw_key))
            if col_name in schema_col_names:
                row_data[col_name] = value

        row_index = len(self.insert_ops)
        self.insert_ops.append((table_name, row_data))

        for arr_key, arr_records in arrays.items():
            child_table_name = schema.child_tables.get(self._sanitize_name(arr_key))

            if child_table_name is None:
                continue

            for child_record in arr_records:
                self._process_record(
                    record=child_record,
                    table_name=child_table_name,
                    parent_id=row_index,   # db_manager bunu gerçek id ile değiştirir
                    parent_table=table_name
                )

        return row_index

    def _sanitize_name(self, name: str) -> str:
        import re
        name = name.strip().lower()
        name = re.sub(r"[^\w]", "_", name)
        name = re.sub(r"_+", "_", name)
        name = name.strip("_")
        return name