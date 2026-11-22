"""Crea (o recrea) la base de PRUEBA mira_nativo_test. No toca ninguna otra base."""
import configparser
import sys

import psycopg2

NAME = "mira_nativo_test"
cfg = configparser.ConfigParser()
cfg.read(sys.argv[1])
o = cfg["options"]
conn = psycopg2.connect(dbname="postgres", user=o["db_user"], password=o.get("db_password", ""),
                        host=o.get("db_host", "localhost"), port=o.get("db_port", "5432"))
conn.autocommit = True
cur = conn.cursor()
cur.execute("SELECT datname, datcollate, datctype FROM pg_database WHERE datname IN (%s, %s)",
            (NAME, o.get("db_name", "odoo")))
print(cur.fetchall())
cur.execute('DROP DATABASE IF EXISTS "%s"' % NAME)
cur.execute("CREATE DATABASE \"%s\" ENCODING 'UTF8' LC_COLLATE 'C' LC_CTYPE 'C' TEMPLATE template0" % NAME)
print("created", NAME)
