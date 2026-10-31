import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import DatabaseManager
from engine.normalizer import Normalizer
from engine.schema_builder import SchemaBuilder


class ConversionTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(os.path.join(self.tmp.name, "test.db"))
        self.db.connect()

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def convert(self, data, root="kayitlar"):
        schemas = SchemaBuilder().build(data, root_table_name=root)
        self.db.create_tables(schemas)
        self.db.insert_all(Normalizer(schemas).generate_inserts(data, root))
        return schemas

    def rows(self, sql):
        return self.db.execute_query(sql)[1]

    def columns(self, table):
        return self.db.get_table_data(table)[0]

    def test_ic_ice_obje_ve_dizi_iliskili_tablolara_donusur(self):
        data = [
            {"ad": "a", "adres": {"sehir": "Kocaeli"},
             "siparisler": [{"no": "S1", "urunler": [{"adi": "Kalem"}]}]},
            {"ad": "b", "adres": {"sehir": "Ankara"},
             "siparisler": [{"no": "S2", "urunler": [{"adi": "Silgi"}]}]},
        ]
        self.convert(data, "musteriler")

        self.assertEqual(
            self.rows(
                "SELECT m.ad, m.adres_sehir, s.no, u.adi FROM musteriler m "
                "JOIN siparisler s ON s.musteriler_id = m.id "
                "JOIN urunler u ON u.siparisler_id = s.id ORDER BY m.id"
            ),
            [("a", "Kocaeli", "S1", "Kalem"), ("b", "Ankara", "S2", "Silgi")],
        )

    def test_id_alani_kaynak_id_sutununda_korunur(self):
        self.convert([{"id": 70, "ad": "x"}, {"ID": 71, "ad": "y"}])

        self.assertEqual(self.columns("kayitlar"), ["id", "kaynak_id", "ad"])
        self.assertEqual(
            self.rows("SELECT id, kaynak_id, ad FROM kayitlar"),
            [(1, 70, "x"), (2, 71, "y")],
        )

    def test_yeniden_adlandirilan_sutun_mevcut_alanla_cakismaz(self):
        self.convert([{"id": 70, "kaynak_id": 5}])

        self.assertEqual(
            self.rows("SELECT id, kaynak_id, kaynak_id_2 FROM kayitlar"),
            [(1, 5, 70)],
        )

    def test_foreign_key_adindaki_alan_bagi_bozmaz(self):
        self.convert({"siparisler": [{"kayitlar_id": 999, "no": "S1"}]})

        self.assertEqual(
            self.rows("SELECT kayitlar_id, kaynak_kayitlar_id, no FROM siparisler"),
            [(1, 999, "S1")],
        )

    def test_id_ile_biten_alanlar_degismeden_kaydedilir(self):
        values = [0, 0, 1, 1, 2]
        self.convert([{"ad": str(i), "user_id": v} for i, v in enumerate(values)])

        self.assertEqual(
            [row[0] for row in self.rows("SELECT user_id FROM kayitlar ORDER BY id")],
            values,
        )

    def test_alt_tablodaki_id_ile_biten_alanlar_da_korunur(self):
        data = [{"ad": "a", "siparisler": [{"no": "S1", "urun_id": 0}, {"no": "S2", "urun_id": 1}]}]
        self.convert(data)

        self.assertEqual(
            self.rows("SELECT kayitlar_id, no, urun_id FROM siparisler ORDER BY id"),
            [(1, "S1", 0), (1, "S2", 1)],
        )

    def test_ilkel_dizi_degerleri_alt_tabloya_aktarilir(self):
        self.convert([{"ad": "x", "etiketler": ["a", "b"]}, {"ad": "y", "etiketler": ["c"]}])

        self.assertEqual(
            self.rows("SELECT kayitlar_id, deger FROM etiketler ORDER BY id"),
            [(1, "a"), (1, "b"), (2, "c")],
        )

    def test_karisik_dizide_ilkel_ve_nesne_elemanlari_korunur(self):
        self.convert({"ogeler": [1, {"ad": "x"}, None]})

        self.assertEqual(
            self.rows("SELECT deger, ad FROM ogeler ORDER BY id"),
            [(1, None), (None, "x"), (None, None)],
        )

    def test_kok_seviyesindeki_ilkel_liste_aktarilir(self):
        self.convert([1, 2, 3])

        self.assertEqual(self.rows("SELECT deger FROM kayitlar ORDER BY id"), [(1,), (2,), (3,)])

    def test_ic_ice_ilkel_diziler_aktarilir(self):
        self.convert({"matris": [[1, 2], [3]]})

        self.assertEqual(
            self.rows(
                "SELECT m.id, d.deger FROM matris m "
                "JOIN deger d ON d.matris_id = m.id ORDER BY d.id"
            ),
            [(1, 1), (1, 2), (2, 3)],
        )

    def test_ayni_dizi_adi_farkli_ust_tablolarda_ayrilir(self):
        data = {
            "bolumler": [{"ad": "B1", "kisiler": [{"isim": "k1"}]}],
            "projeler": [{"ad": "P1", "kisiler": [{"sure": 3}]}],
        }
        self.convert(data)

        self.assertEqual(
            self.rows(
                "SELECT b.ad, k.isim FROM bolumler b "
                "JOIN kisiler k ON k.bolumler_id = b.id"
            ),
            [("B1", "k1")],
        )
        self.assertEqual(
            self.rows(
                "SELECT p.ad, k.sure FROM projeler p "
                "JOIN projeler_kisiler k ON k.projeler_id = p.id"
            ),
            [("P1", 3)],
        )

    def test_dizi_adi_kok_tabloyla_cakismaz(self):
        self.convert([{"ad": "a", "urunler": [{"adi": "Kalem"}]}], "urunler")

        self.assertEqual(
            self.rows(
                "SELECT u.ad, a.adi FROM urunler u "
                "JOIN urunler_urunler a ON a.urunler_id = u.id"
            ),
            [("a", "Kalem")],
        )

    def test_kendi_icinde_tekrar_eden_dizi_adi_desteklenir(self):
        data = {"dallar": [{"ad": "kok", "dallar": [{"ad": "yaprak"}]}]}
        self.convert(data)

        self.assertEqual(
            self.rows(
                "SELECT d.ad, c.ad FROM dallar d "
                "JOIN dallar_dallar c ON c.dallar_id = d.id"
            ),
            [("kok", "yaprak")],
        )


if __name__ == "__main__":
    unittest.main()
