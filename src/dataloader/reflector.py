from dataloader import db
from dataloader import helper
from dataloader import logging
from dataloader.helper import FileUtil
from dataloader.error import UnsupportError

logger = logging.getLogger(__name__)


def _create_module_base(root_path, dbname, tb_rows):
    """ Create target/<dbname>/__init__.py and import iter_<tbname>s """
    module_base = helper.make_dir(root_path, 'target/' + dbname, True)
    fp = FileUtil(helper.full_pyfile_name(module_base, '__init__'))
    for row in tb_rows:
        fp.writeline("from ." + row[0] + " import iter_" + row[0])
    fp.saveall()

    return module_base


def _enum_choice(db_session, typid):
    """ Fetch enum type values """
    ln = '(['
    for i in db_session.execute(
        "SELECT enumlabel FROM pg_enum WHERE enumtypid=%s" % typid
    ).fetchall():
        ln += "'" + i.enumlabel + "',"

    return ln[:-1] + '])'


def _create_table_object_and_factory(dbcfg, path, tbname, full_tbname, rows):
    fuzzer = {
        'array': '"[]"',
        'bytea': 'factories.FuzzyText()',
        'varchar': 'factories.FuzzyText()',
        'bool': 'factories.FuzzyBoolean()',
        'jsonb': '"{}"',
        'timestamp': 'datetime.now(tz=UTC)',
        'uuid': 'factories.FuzzyUuid()'
    }
    db_session = dbcfg['session']
    camel_tbname = helper.to_camel_case(tbname)

    # create <tbname>.py
    fp = FileUtil(helper.full_pyfile_name(path, tbname))

    # import dependencies
    fp.writeline("import uuid")
    fp.writeline("from pytz import UTC")
    fp.writeline("from datetime import datetime")

    fp.blankline()

    fp.writeline("import fastrand")
    fp.writeline("import factory")
    fp.writeline("from factory import fuzzy")
    fp.writeline("from dataloader import db")
    fp.writeline("from dataloader import factories")
    
    fp.blankline()
    fp.writeline("NONECOL = '-*None*-'")

    # init a db_session
    fp.writeline("db_session = db.init_session('" + dbcfg['url'] + "')")

    fp.blankline(2)

    # def _detect_maxv(tbname, col):
    fp.writeline("def _detect_maxv(tbname, col):")
    fp.writeline("sql = 'SELECT MAX(' + col + ') FROM ' + tbname", 4)
    fp.writeline("maxv = db_session.query(sql).scalar() or 0", 4)
    fp.blankline()
    fp.writeline("return maxv", 4)

    fp.blankline(2)

    # Generate <tbname> Data Object
    fp.writeline("class " + camel_tbname + "(object):")
    fp.writeline("__table_name__ = '" + tbname + "'", 4)
    fp.writeline("__ftable_name__ = '" + full_tbname + "'", 4)
    
    fp.blankline()
    
    #        def __init__(*args, **kwargs):
    line = "def __init__(self"
    for row in rows:
        line += ", " + row[0]
    line += "):"
    fp.writeline(line, 4)
    for row in rows:
        fp.writeline("self." + row[0] + " = " + row[0], 8)
    
    fp.blankline()

    #        def insert(cls):
    fp.writeline("@classmethod", 4)
    fp.writeline("def insert(cls):", 4)
    line = "return 'INSERT INTO " + full_tbname + "(" + rows[0][0]
    for i in range(1, len(rows)):
        line += ", " + rows[i][0]
    line += ") VALUES '"
    fp.writeline(line, 8)

    fp.blankline()

    #        def value(self):
    fp.writeline("def value(self):", 4)
    line = "return '(%" + ('d' if rows[0][1].startswith('int') else 's')
    for i in range(1, len(rows)):
        line += ", %" + ('d' if rows[i][1].startswith('int') else 's')
    line += ")' % (self." + rows[0][0]
    for i in range(1, len(rows)):
        line += ", self." + rows[i][0]
    line += ")"
    fp.writeline(line, 8)

    fp.blankline()

    #        def csvalue(self):
    fp.writeline("def csvalue(self):", 4)
    line = "return (self." + rows[0][0]
    for i in range(1, len(rows)):
        line += ", self." + rows[i][0]
    line += ")"
    fp.writeline(line, 8)

    fp.blankline(2)

    # Generate <tbname>Factory Object
    fp.writeline("class " + camel_tbname + "Factory(factory.Factory):")
    fp.writeline("class Meta:", 4)
    fp.writeline("model = " + camel_tbname, 8)
    fp.blankline()
    for row in rows:
        typ = row[1].replace('_', '')[:-2]
        line = row[0] + " = "
        if typ == 'enum':
            line += "factory.fuzzy.FuzzyChoice" + _enum_choice(db_session, row[3])
        elif typ.startswith('int'):
            line += "fastrand.pcg32bounded(" + '9'.rjust(row[2], '9') + ")"
        else:
            line += fuzzer.get(typ, "factories.FuzzyText()")
        fp.writeline(line, 4)

    fp.blankline(2)

    #        def _build(**kwargs):
    fp.writeline("def _build(**kwargs):")
    fp.writeline("f = " + camel_tbname + "Factory(**kwargs)", 4)
    fp.blankline()
    fp.writeline("return f", 4)

    fp.blankline(2)

    #        def _build_sql(insert, **kwargs):
    fp.writeline("def _build_sql(insert, **kwargs):")
    fp.writeline("f = " + camel_tbname + "Factory(**kwargs)", 4)
    fp.writeline("if insert:", 4)
    fp.writeline("return " + camel_tbname + ".insert() + f.value()", 8)
    fp.blankline()
    fp.writeline("return f.value()", 4)

    fp.blankline(2)

    # def iter_<tbname>():
    fp.writeline(
        "def iter_" + tbname + "(count, auto_incr_cols=[NONECOL], **kwargs):"
    )
    fp.writeline("if not isinstance(count, int):", 4)
    fp.writeline("raise ValueError('count must be integer and gt. 0')", 8)
    
    fp.blankline()
    
    fp.writeline("count = 2 if count<1 else count+1", 4)
    fp.writeline("for i in range(1, count):", 4)
    fp.writeline("for k in auto_incr_cols:", 8)
    fp.writeline("if k == NONECOL:", 12)
    fp.writeline("continue", 16)
    fp.writeline("kwargs[k] = i + _detect_maxv(k, '" + tbname + "')", 12)
    
    fp.blankline()
    
    fp.writeline("yield _build(**kwargs)", 8)

    fp.blankline(2)

    # def iter_<tbname>_v2():
    fp.writeline("def iter_" + tbname + "_v2(count, **kwargs):")
    fp.writeline("if not isinstance(count, int):", 4)
    fp.writeline("raise ValueError('count must be integer and gt. 0')", 8)
    fp.blankline()
    fp.writeline("yield _build_sql(True, **kwargs)", 4)
    fp.blankline()
    fp.writeline("count = 1 if count < 1 else count", 4)
    fp.writeline("for i in range(count):", 4)
    fp.writeline("yield _build_sql(False, **kwargs)" , 8)

    fp.saveall()


def _reflect(root_path, dbcfg):
    """ reflect for one database """
    db_session = dbcfg['session']
    columns_sql = dbcfg['columns_sql']
    
    tb_rows = db_session.execute(dbcfg['tables_sql']).fetchall()

    path = _create_module_base(root_path, dbcfg['database'], tb_rows)

    tables = set()
    for tb_row in tb_rows:
        tables.add(tb_row[1])

        col_sql = columns_sql % tb_row[0]
        col_rows = db_session.execute(col_sql).fetchall()
        
        _create_table_object_and_factory(
            dbcfg, path, tb_row[0], tb_row[1], col_rows
        )

    return tables
        

def reflect_targets(import_name, databases):
    """ Called when init DataLoader """
    root_path = helper.get_root_path(import_name)
    for dbname in databases.keys():
        dbcfg = databases[dbname]
        try:
            if dbcfg['scheme'] not in ('mysql', 'postgresql'):
                raise UnsupportError(
                    f"The type {dbcfg['scheme']} of database is not supported at this moment."
                )
            
            dbcfg['session'] = db.init_session(dbcfg['url'])
            dbcfg['tables'] = _reflect(root_path, dbcfg)
        except Exception as exc:
            logger.exception(
                f"[Reflect] Failed to reflect target of database {dbcfg['database']}({dbcfg['scheme']}): {exc}"
            )