import sqlite3
from pathlib import Path
from engine.schema_builder import ParentRef, TableSchema


class DatabaseManager:
    # db dosya yolu ve bağlantıları basta none cunku baglanmadan sorgu yapılmaz
    def __init__(self, db_path: str = "output.db"):
        
        self.db_path = db_path
        self.conn: sqlite3.Connection = None
        self.cursor: sqlite3.Cursor = None

        # db bağlanır dosya yoksa SQLite ile otomatik oluşturur
    
    def connect(self):
        
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA foreign_keys = ON")#foreign key aktif edilir
        self.cursor = self.conn.cursor()

    # Açık olan bağlantıyı kapatır
    def close(self):
        
        if self.conn:
            self.conn.close()
            self.conn = None
            self.cursor = None
   
    #db deki tum tabloları siler 
    def reset(self):
        if not self.conn:
            self.connect()

        self.cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = [row[0] for row in self.cursor.fetchall()] #silinecek tabloların iisimlerini getiri

        self.conn.execute("PRAGMA foreign_keys = OFF") #foreign key kapatılır birbirine baglı tablolar silinirken sorun çıkmasın diye
        for table in tables:
            self.cursor.execute(f'DROP TABLE IF EXISTS "{table}"')
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.commit()

    # tablo olusturma
    def create_tables(self, schemas: list[TableSchema]):
        if not self.conn:
            self.connect()

        for schema in schemas:
            sql = schema.to_create_sql()
            self.cursor.execute(sql)

        self.conn.commit()

    def insert_all(self, insert_ops: list[tuple[str, dict]]) -> dict[int, int]:
        if not self.conn:
            self.connect()

        id_map: dict[int, int] = {} # gecici sıra no sqlite ın atadıgı gerçek id ile eşleştirilir

        for index, (table_name, row_data) in enumerate(insert_ops):

            resolved_row = {}
            for col, val in row_data.items():
                if isinstance(val, ParentRef):
                    resolved_row[col] = id_map[val.index]
                else:
                    resolved_row[col] = val

            if not resolved_row:
                self.cursor.execute(f'INSERT INTO "{table_name}" DEFAULT VALUES')
            else:
                # Sütun adları ve değerler ayrı tutularak güvenli INSERT yapılır
                columns = ", ".join(f'"{c}"' for c in resolved_row.keys())
                placeholders = ", ".join("?" for _ in resolved_row)
                values = list(resolved_row.values())
                self.cursor.execute(
                    f'INSERT INTO "{table_name}" ({columns}) VALUES ({placeholders})',
                    values
                )

            id_map[index] = self.cursor.lastrowid

        self.conn.commit()
        return id_map
    
    # Veritabanındaki tüm tablo adlarını döndürür
    def get_all_tables(self) -> list[str]:
       
        if not self.conn:
            self.connect()

        self.cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        return [row[0] for row in self.cursor.fetchall()]
    
    # Seçilen tablonun tüm sütun adlarını ve satırlarını döndürür 
    def get_table_data(self, table_name: str) -> tuple[list[str], list[tuple]]:
        
        if not self.conn:
            self.connect()

        self.cursor.execute(f'SELECT * FROM "{table_name}"')
        columns = [desc[0] for desc in self.cursor.description]
        rows = self.cursor.fetchall()
        return columns, rows
    
   # Kullanıcının yazdığı SQL sorgusunu çalıştırır ve sonucu döndürür
    def execute_query(self, sql: str) -> tuple[list[str], list[tuple]]:
     
        if not self.conn:
            self.connect()

        sql_upper = sql.strip().upper()
        if not sql_upper.startswith("SELECT"):
            raise ValueError("Sadece SELECT sorguları çalıştırılabilir.")

        self.cursor.execute(sql)
        columns = [desc[0] for desc in self.cursor.description]
        rows = self.cursor.fetchall()
        return columns, rows
    
    # Tablonun CREATE TABLE SQL'ini döndürür 
    def get_table_schema_sql(self, table_name: str) -> str:
        
        self.cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        result = self.cursor.fetchone()
        return result[0] if result else ""