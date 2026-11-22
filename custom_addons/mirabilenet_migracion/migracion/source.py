"""Lectura del sistema anterior (PostgreSQL de Django). Solo lee: nunca escribe en el origen."""
import re
from datetime import datetime, timezone

from psycopg2 import sql

_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")


class SourceError(Exception):
    pass


def _naive_utc(value):
    """Odoo guarda instantes en UTC y sin zona: así se entregan los del origen."""
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


class SourceReader:
    """Lee tablas del origen con un cursor: el de una conexión aparte a la copia de la base,
    o, en las pruebas, el de la propia base con las tablas en un esquema aparte."""

    def __init__(self, cursor, schema="public"):
        if not _NAME.match(schema):
            raise SourceError("Esquema no válido: %s" % schema)
        self.cr = cursor
        self.schema = schema

    def _table(self, table):
        if not _NAME.match(table):
            raise SourceError("Tabla no válida: %s" % table)
        return sql.Identifier(self.schema, table)

    def columns(self, table):
        self.cr.execute("SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = %s AND table_name = %s", [self.schema, table])
        return {row[0] for row in self.cr.fetchall()}

    def require(self, table, columns):
        """Antes de migrar se comprueba que el origen tiene lo que se va a leer."""
        found = self.columns(table)
        if not found:
            raise SourceError("El origen no tiene la tabla %s." % table)
        missing = sorted(set(columns) - found)
        if missing:
            raise SourceError("A la tabla %s le faltan columnas: %s" % (table, ", ".join(missing)))

    def rows(self, table, columns, where=None, params=()):
        self.require(table, set(columns) | {"id"})
        query = sql.SQL("SELECT {cols} FROM {table}").format(
            cols=sql.SQL(", ").join(sql.Identifier(c) for c in ["id"] + list(columns)),
            table=self._table(table))
        if where:
            query += sql.SQL(" WHERE ") + sql.SQL(where)
        query += sql.SQL(" ORDER BY id")
        self.cr.execute(query, params)
        names = ["id"] + list(columns)
        return [dict(zip(names, [_naive_utc(v) for v in row])) for row in self.cr.fetchall()]

    def scalar(self, query, params=()):
        """Una cuenta o una suma de control. La consulta usa {schema} para el esquema."""
        self.cr.execute(sql.SQL(query).format(schema=sql.Identifier(self.schema)), params)
        return self.cr.fetchone()[0]
