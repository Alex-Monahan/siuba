# sqlvariant, allow defining 3 namespaces to override defaults
from ..translate import (
        SqlColumn, SqlColumnAgg, SqlTranslations, 
        win_agg, win_over, win_cumul, sql_scalar, sql_agg,
        RankOver,
        wrap_annotate, annotate,
        create_sql_translators
        )

from .base import base_scalar, base_win, base_agg

import sqlalchemy.sql.sqltypes as sa_types
from sqlalchemy import sql


# Custom dispatching in call trees ============================================

class PostgresqlColumn(SqlColumn): pass

class PostgresqlColumnAgg(SqlColumnAgg, PostgresqlColumn): pass

# Custom translations =========================================================

def returns_float(ns, func_names):
    return {k: wrap_annotate(ns[k], result_type = "float") for k in func_names}

def sql_log(col, base = None):
    if base is None:
        return sql.func.ln(col)
    return sql.func.log(col)

@annotate(result_type = "float")
def sql_round(col, n):
    return sql.func.round(col, n)

def sql_func_contains(col, pat, case = True, flags = 0, na = None, regex = True):
    # TODO: warn there differences in regex for python and sql?
    # TODO: validate pat is string?
    if not isinstance(pat, str):
        raise TypeError("pat argument must be a string")
    if flags != 0 or na is not None:
        raise NotImplementedError("flags and na options not supported")

    if not regex:
        case_col = col if case else col.lower()
        return case_col.contains(pat, autoescape = True)

    full_op = "~" if case else "~*"

    return col.op(full_op)(pat)

def sql_func_truediv(x, y):
    return sql.cast(x, sa_types.Float()) / y

def sql_func_floordiv(x, y):
    return sql.cast(x / y, sa_types.Integer())

def sql_func_rank(col):
    # see https://stackoverflow.com/a/36823637/1144523
    min_rank = RankOver(sql.func.rank(), order_by = col)
    to_mean = (RankOver(sql.func.count(), partition_by = col) - 1) / 2.0

    return min_rank + to_mean

scalar = SqlTranslations(
        base_scalar,

        # TODO: remove log, not a pandas method
        log = sql_log,

        # TODO: bring up to date (not pandas methods)
        concat = lambda col: sql.func.concat(col),
        cat = lambda col: sql.func.concat(col),
        str_c = lambda col: sql.func.concat(col),

        # infix and infix methods ----

        __div__ = sql_func_truediv,
        div = sql_func_truediv,
        divide = sql_func_truediv,
        rdiv = lambda x,y: sql_func_truediv(y, x),
        __rdiv__ = lambda x, y: sql_func_truediv(y, x),

        __truediv__ = sql_func_truediv,
        truediv = sql_func_truediv,
        __rtruediv__ = lambda x, y: sql_func_truediv(y, x),

        __floordiv__ = sql_func_floordiv,
        __rfloordiv__ = lambda x, y: sql_func_floordiv(y, x),

        round = sql_round,
        __round__ = sql_round,

        **{
            "str.contains": sql_func_contains,
        },
        **returns_float(base_scalar, [
             "dt.day", "dt.dayofweek", "dt.dayofyear", "dt.days_in_month",
             "dt.daysinmonth", "dt.hour", "dt.minute", "dt.month",
             "dt.quarter", "dt.second", "dt.week", "dt.weekday",
             "dt.weekofyear", "dt.year"
             ]),
        )

window = SqlTranslations(
        base_win,
        any = annotate(win_agg("bool_or"), input_type = "bool"),
        all = annotate(win_agg("bool_and"), input_type = "bool"),
        lag = win_agg("lag"),
        std = win_agg("stddev_samp"),
        var = win_agg("var_samp"),

        # overrides ----

        # note that postgres does sum(bigint) -> numeric
        sum = annotate(win_agg("sum"), result_type = "float"),
        cumsum = annotate(win_cumul("sum"), result_type = "float"),
        rank = sql_func_rank,
        size = win_agg("count"),     #TODO double check
        )

aggregate = SqlTranslations(
        base_agg,
        all = sql_agg("bool_and"),
        any = sql_agg("bool_or"),
        std = sql_agg("stddev_samp"),
        var = sql_agg("var_samp"),

        sum = annotate(sql_agg("sum"), result_type = "float"),
        )


funcs = dict(scalar = scalar, aggregate = aggregate, window = window)

# translate(config, CallTreeLocal, PostgresqlColumn, _.a + _.b)
translator = create_sql_translators(
        scalar, aggregate, window,
        PostgresqlColumn, PostgresqlColumnAgg
        )
