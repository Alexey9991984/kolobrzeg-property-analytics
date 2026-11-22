import argparse
import csv
import hashlib
import io
import re
from pathlib import Path

import psycopg2
from psycopg2 import sql

parser = argparse.ArgumentParser()
parser.add_argument("csv_file", type=Path)
parser.add_argument("--db", default="host=localhost dbname=kolobrzeg_property_analytics_v2 user=postgres")
args = parser.parse_args()
raw = args.csv_file.read_bytes()
digest = hashlib.sha256(raw).hexdigest()
reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), delimiter=";", strict=True)
header = next(reader)
cols = [re.search(r"\(([a-z_]+)\)$", name)[1] for name in header]
keys = ["tran_lokalny_id_iip", "typ_przedmiotu", "id_przedmiotu"]
assert len(cols) == 35 and len(set(cols)) == 35 and set(keys + ["dok_data", "adres", "bud_pow_uzyt"]) <= set(cols)
rows = list(reader)
assert rows and all(len(row) == len(cols) for row in rows)
for row in rows:
    assert all(row[cols.index(key)] not in ("", "brak danych") for key in keys)
names = sql.SQL(", ").join(map(sql.Identifier, cols))
key_list = sql.SQL(", ").join(map(sql.Identifier, keys))
column_defs = sql.SQL(", ").join(sql.SQL("{} text").format(sql.Identifier(col)) for col in cols)
updates = sql.SQL(", ").join(sql.SQL("{0} = excluded.{0}").format(sql.Identifier(col)) for col in cols if col not in keys)
payload = io.StringIO(newline="")
csv.writer(payload, delimiter=";").writerows(rows)
payload.seek(0)
with psycopg2.connect(args.db, connect_timeout=5) as conn:
    with conn.cursor() as cur:
        cur.execute("select pg_advisory_xact_lock(hashtext('kolobrzeg.rcn.full_export'))")
        cur.execute("create schema if not exists rcn")
        cur.execute("""create table if not exists rcn.loads (
            sha256 text primary key, filename text not null, source_rows integer not null,
            loaded_at timestamptz not null default now())""")
        cur.execute(sql.SQL("create table if not exists rcn.object_rows ({}, primary key ({}))").format(column_defs, key_list))
        cur.execute("select 1 from rcn.loads where sha256=%s", (digest,))
        if cur.fetchone() is None:
            cur.execute("create temp table rcn_stage (like rcn.object_rows including indexes) on commit drop")
            cur.copy_expert(sql.SQL("copy rcn_stage ({}) from stdin with (format csv, delimiter ';', force_not_null ({}))").format(names,names), payload)
            cur.execute(sql.SQL("insert into rcn.object_rows ({0}) select {0} from rcn_stage on conflict ({1}) do update set {2}").format(names,key_list,updates))
            cur.execute("insert into rcn.loads (sha256,filename,source_rows) values (%s,%s,%s)", (digest,args.csv_file.name,len(rows)))
            print("Loaded",len(rows))
        else:
            print("Already loaded",len(rows))
        cur.execute("""
        create or replace view rcn.report_objects as
        with versions as (
          select *, regexp_replace(tran_lokalny_id_iip, '/[0-9]{4}-[0-9]{2}-[0-9]{2}T[^/]+Z$', '') as stable_id
          from rcn.object_rows
        ), latest as (
          select stable_id, max(tran_lokalny_id_iip) as latest_id from versions group by stable_id
        ), typed as (
          select v.*, to_date(dok_data, 'DD.MM.YYYY') as document_date,
            nullif(split_part(nullif(adres,'brak danych'), ',', 1),'') as locality,
            case when replace(bud_pow_uzyt,',','.') ~ '^[0-9]+([.][0-9]+)?$' then replace(bud_pow_uzyt,',','.')::float8 end as area,
            case when replace(tran_cena_brutto,',','.') ~ '^[0-9]+([.][0-9]+)?$' then replace(tran_cena_brutto,',','.')::float8 end as price
          from versions v join latest l on v.stable_id=l.stable_id and v.tran_lokalny_id_iip=l.latest_id
        )
        select typed.*, extract(year from document_date)::bigint as "Год", locality as "Населённый пункт",
          area as "Полезная площадь, м²", price as "Цена сделки, PLN",
          case when typ_przedmiotu='Budynki' and bud_rodzaj='mieszkalny'
            and nier_rodzaj='nieruchomość gruntowa zabudowana' and nier_udzial='1/1'
            and tran_rodzaj_trans='wolny rynek' and tran_rodzaj_rynku='rynek wtórny'
            and area between 100 and 150 then 'Да' else 'Нет' end as "Кандидат 100–150 м²"
        from typed
        """)
        cur.execute("""
        create or replace view rcn.report_transactions as
        select tran_lokalny_id_iip as "ID сделки", min(document_date) as "Дата документа",
          min("Год") as "Год", min(nullif(adres,'brak danych')) as "Адрес",
          min(locality) as "Населённый пункт", min(tran_rodzaj_rynku) as "Рынок",
          min(tran_rodzaj_trans) as "Вид сделки", max(price) as "Цена сделки, PLN",
          count(*) as "Объектов",
          case when bool_or("Кандидат 100–150 м²"='Да') then 'Да' else 'Нет' end as "Кандидат 100–150 м²"
        from rcn.report_objects group by tran_lokalny_id_iip
        """)
        cur.execute("""select (select count(*) from rcn.report_objects),
            (select count(*) from rcn.report_transactions),
            (select count(*) from rcn.report_transactions where "Кандидат 100–150 м²"='Да')""")
        print("Objects, transactions, house candidates:",cur.fetchone())
