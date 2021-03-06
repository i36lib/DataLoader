from dataloader import db
from dataloader import helper
from dataloader import logging
from dataloader.helper import FileUtil

logger = logging.getLogger(__name__)


def _create_module_base(root_path, dbname, tb_rows):
    """ Create target/<dbname>/__init__.py and import iter_<tbname>s """
    module_base = helper.make_dir(root_path, 'target/' + dbname, True)
    fp = FileUtil(helper.full_pyfile_name(module_base, '__init__'))
    for row in tb_rows:
        camel_tbname = helper.to_camel_case(row[0])
        fp.writeline("from ." + row[0] + " import " + camel_tbname)
        fp.writeline("from ." + row[0] + " import iter_" + row[0])
    fp.saveall()

    return module_base


def _enum_choice(db_session, typid):
    """ Fetch enum type values """
    ln = '(['
    for i in db_session.execute(
        "SELECT enumlabel FROM pg_enum WHERE enumtypid='%s'" % typid
    ).fetchall():
        ln += "'" + i.enumlabel + "',"

    return ln[:-1] + '])'


def _create_table_object_and_factory(
    dbcfg, path, tbname, full_tbname, rows, pkey_rows
):
    fuzzer = dbcfg['data_types']
    db_session = dbcfg['session']
    camel_tbname = helper.to_camel_case(tbname)

    # create <tbname>.py
    fp = FileUtil(helper.full_pyfile_name(path, tbname))

    # import dependencies
    fp.writeline("import uuid")
    fp.writeline("import copy")
    fp.writeline("from pytz import UTC")
    fp.writeline("from datetime import datetime")

    fp.blankline()

    fp.writeline("import factory")
    fp.writeline("from factory import fuzzy")
    fp.writeline("from dataloader import db")
    fp.writeline("from dataloader import factories")
    fp.writeline("from dataloader.helper import Cache, AutoUUID")

    fp.blankline()

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
    fp.writeline("__dbcfg_ref__ = None", 4)
    fp.writeline("__retain_pkey__ = False", 4)
    fp.writeline("__table_name__ = '" + tbname + "'", 4)
    fp.writeline("__ftable_name__ = '" + full_tbname + "'", 4)

    line = "\"\"\"LOAD DATA LOCAL INFILE '%s' REPLACE "
    line += "INTO TABLE " + full_tbname + " FIELDS TERMINATED BY '|'"
    line += " LINES TERMINATED BY '\n'\"\"\""
    fp.writeline("__load_mysql__ = " + line, 4)

    fp.blankline()

    #        def __init__(*args, **kwargs):
    line = "def __init__(self"
    for row in rows:
        line += ", " + row[0]
    line += ", retain_pkey=False):"
    fp.writeline(line, 4)
    fp.writeline("self.__class__.__retain_pkey__ = retain_pkey", 8)
    fp.blankline()
    for row in rows:
        fp.writeline("self." + row[0] + " = " + row[0], 8)

    fp.blankline()

    #        def pkey_value_map(self):
    fp.writeline("def pkey_value_map(self):", 4)
    fp.writeline("return {", 8)
    for i in range(len(pkey_rows)):
        fp.writeline("'" + rows[i][0] + "': self." + rows[i][0] + ",", 12)
    fp.writeline("}", 8)

    fp.blankline(2)

    #        def tuple_value(self):
    fp.writeline("def tuple_value(self):", 4)
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
        line = row[0] + " = "

        typ = row[5].replace('_', '')[:-2]
        if typ == 'enum':
            line += ("factory.fuzzy.FuzzyChoice" + _enum_choice(db_session, row[3]))
        elif typ == 'array':
            line += fuzzer.get("array", "None")
        else:
            line += fuzzer.get(row[1], "None")
        fp.writeline(line, 4)

    fp.blankline(2)

    # def iter_<tbname>():
    fp.writeline(
        "def iter_" + tbname + "(count, retaining=False, auto_incr_cols=[], **kwargs):"
    )
    fp.writeline("if not isinstance(count, int):", 4)
    fp.writeline("raise ValueError('count must be integer and gt. 0')", 8)

    fp.blankline()

    fp.writeline("count = 1 if count<1 else count", 4)

    fp.writeline("for i, k in enumerate(auto_incr_cols):", 4)
    fp.writeline("kwargs[k] = _detect_maxv(k, '" + tbname + "')", 8)

    fp.blankline()
    fp.writeline("for i in range(count):", 4)
    fp.writeline("for k in auto_incr_cols:", 8)
    fp.writeline("kwargs[k] += 1", 12)

    fp.blankline()

    fp.writeline("kwgs = copy.copy(kwargs)", 8)
    fp.writeline("for k, v in kwgs.items():", 8)
    fp.writeline("if isinstance(v, Cache):", 12)
    fp.writeline("kwgs[k] = v.value(i)", 16)
    fp.writeline("if kwgs[k] is None:", 16)
    fp.writeline("kwgs.pop(k)", 20)
    fp.writeline("elif isinstance(v, AutoUUID):", 12)
    fp.writeline("kwgs[k] = v.uuid_ + str(i).rjust(8, '0')", 16)

    fp.blankline()

    fp.writeline("yield " + camel_tbname + "Factory(retain_pkey=retaining, **kwgs)", 8)

    fp.saveall()


def _reflect(root_path, dbcfg):
    """ reflect for one database """
    db_session = dbcfg['session']
    pkey_sql = dbcfg['pkey_sql']
    columns_sql = dbcfg['columns_sql']

    tb_rows = db_session.execute(dbcfg['tables_sql']).fetchall()

    path = _create_module_base(root_path, dbcfg['database'], tb_rows)

    tables = set()
    for tb_row in tb_rows:
        tables.add(tb_row[1])

        col_sql = columns_sql % tb_row[0]
        pky_sql = pkey_sql % tb_row[0]

        col_rows = db_session.execute(col_sql).fetchall()
        pkey_rows = db_session.execute(pky_sql).fetchall()

        _create_table_object_and_factory(
            dbcfg, path, tb_row[0], tb_row[1], col_rows, pkey_rows
        )

    return tables


def reflect_targets(import_name, databases):
    """ Called when init DataLoader """
    root_path = helper.get_root_path(import_name)
    for dbname in databases.keys():
        dbcfg = databases[dbname]
        try:
            dbcfg['session'] = db.init_session(dbcfg['url'])
            dbcfg['tables'] = _reflect(root_path, dbcfg)
        except Exception as exc:
            logger.exception(
                f"[Reflect] Failed to reflect target of database {dbcfg['database']}({dbcfg['scheme']}): {exc}"
            )
            raise exc
