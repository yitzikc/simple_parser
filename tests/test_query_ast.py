import os
import sys
import decimal
import datetime
import operator
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", 'simple_query'))

from query_ast import QueryAst, Comparison, LogicalOperator

EXPECTED_FILENAME = "<web request>"

CONVERTERS = {
    "count": int,
    "length": float,
    "date": datetime.date.fromisoformat,
    "cost": decimal.Decimal
}

def verify_bad_syntax_reported(expression: str, expected_msg: str = None) -> None:
    with pytest.raises(SyntaxError) as se:
        QueryAst(expression, CONVERTERS)

    assert se.value.filename == EXPECTED_FILENAME
    assert se.value.text in expression.splitlines()
    assert se.value.offset <= len(expression)
    if expected_msg is not None:
        assert se.value.msg == expected_msg
    return

def test_single_comparison():
    q = QueryAst("date eq '2019-08-18'", CONVERTERS)
    assert q.ast == Comparison(operator.eq, "date", datetime.date(2019, 8, 18))

    # Make sure case is ignored in field names
    q = QueryAst("COUNT gt 34", CONVERTERS)
    assert(q.ast == Comparison(operator.gt, "count", 34))

    q = QueryAst("Length lt 12.25", CONVERTERS)
    assert(q.ast == Comparison(operator.lt, "length", 12.25))

    # Test that double quotes also work
    q = QueryAst('date ne "2019-05-01"', CONVERTERS)
    assert(q.ast == Comparison(operator.ne, "date", datetime.date(2019, 5, 1)))

    q = QueryAst("  cost le '19.99'", CONVERTERS)
    assert(q.ast == Comparison(operator.le, "cost", decimal.Decimal("19.99")))

    q = QueryAst("\tcost ge 7.5", CONVERTERS)
    assert(q.ast == Comparison(operator.ge, "cost", decimal.Decimal(7.5)))

    # Verify that C-Style comparison operators could also be used
    assert QueryAst("count == 1", CONVERTERS).ast == Comparison(operator.eq, "count", 1)
    assert QueryAst("count != 1", CONVERTERS).ast == Comparison(operator.ne, "count", 1)
    assert QueryAst("count > 1",  CONVERTERS).ast == Comparison(operator.gt, "count", 1)
    assert QueryAst("count < 1",  CONVERTERS).ast == Comparison(operator.lt, "count", 1)
    assert QueryAst("count >= 1", CONVERTERS).ast == Comparison(operator.ge, "count", 1)
    assert QueryAst("count <= 1", CONVERTERS).ast == Comparison(operator.le, "count", 1)

    # Verify that negative numbers also work
    assert QueryAst("count == -1",    CONVERTERS).ast == Comparison(operator.eq, "count", -1)
    assert QueryAst("length >= -1.3", CONVERTERS).ast == Comparison(operator.ge, "length", -1.3)
    assert QueryAst("cost gt -1.32", CONVERTERS).ast == Comparison(operator.gt, "cost", decimal.Decimal(-1.32))
    assert QueryAst("cost lt '-1.75'", CONVERTERS).ast == Comparison(operator.lt, "cost", decimal.Decimal(-1.75))

    # Verify that double negation works
    assert QueryAst("count == - -1",    CONVERTERS).ast == Comparison(operator.eq, "count", 1)
    return

def test_logical_at_default_precedence():
    q = QueryAst("date eq '2019-08-18' AND count lt 20", CONVERTERS)
    assert q.ast == LogicalOperator(operator.and_,(
        Comparison(operator.eq, "date", datetime.date(2019, 8, 18)),
        Comparison(operator.lt, "count", 20)
    ))

    q = QueryAst("date eq '2019-08-18' AND count lt 20 AND cost ge 10.5", CONVERTERS)
    assert q.ast == LogicalOperator(operator.and_,(
        Comparison(operator.eq, "date",  datetime.date(2019, 8, 18)),
        Comparison(operator.lt, "count", 20),
        Comparison(operator.ge, "cost",  decimal.Decimal(10.5))
    ))

    # Test 'or', with mixed case operands
    q = QueryAst("date Eq '2019-08-18' or count lt 20 Or cost GE 10.5", CONVERTERS)
    assert q.ast == LogicalOperator(operator.or_,(
        Comparison(operator.eq, "date",  datetime.date(2019, 8, 18)),
        Comparison(operator.lt, "count", 20),
        Comparison(operator.ge, "cost",  decimal.Decimal(10.5))
    ))

    q = QueryAst("date eq '2019-08-18' AND count lt 20 AND NOT cost ge 10.5", CONVERTERS)
    assert q.ast == LogicalOperator(operator.and_, (
        Comparison(operator.eq, "date",  datetime.date(2019, 8, 18)),
        Comparison(operator.lt, "count", 20),
        LogicalOperator(operator.not_, (
            Comparison(operator.ge, "cost", decimal.Decimal(10.5)),
        )
    )))

    return

def test_malformed():
    with pytest.raises(NameError, match="No such field 'size'"):
        QueryAst("size gt 3", CONVERTERS)

    # Unbalanced quotes
    verify_bad_syntax_reported("date eq '2019-05-01", "EOL while scanning string literal")
    verify_bad_syntax_reported('date eq "2019-05-01', "EOL while scanning string literal")

    # Unexpected value
    verify_bad_syntax_reported("count eq ()", "Value is not a number or a string")
    verify_bad_syntax_reported("count eq num", "Value is not a number or a string")

    # Unknown operator
    verify_bad_syntax_reported("count is 3", "Unknown comparison operator 'is'")
    verify_bad_syntax_reported("count >> 3", "Unsupported expression")
    verify_bad_syntax_reported("count eq 3, length eq 2.4", "Unsupported expression")
    verify_bad_syntax_reported("count eq 3 size eq 4")
    verify_bad_syntax_reported("count eq 3 ; size eq 4")

    # Malformed negative
    verify_bad_syntax_reported("cost gt -'1.75'", "Attempt to negate non-number")
    return

def test_parens():
    ex = "(date eq '2016-05-01') AND ((cost ge 20) OR (cost lt 10.0))"
    q = QueryAst(ex, CONVERTERS)
    assert q.ast == LogicalOperator(operator.and_, (
        Comparison(operator.eq, "date",  datetime.date(2016, 5, 1)),
        LogicalOperator(operator.or_, (
            Comparison(operator.ge, "cost", decimal.Decimal(20)),
            Comparison(operator.lt, "cost", decimal.Decimal(10))
        )
    )))

    # Make sure superfluous parentheses have no effect
    for n in range(2,5):
        ex_superflouous_parens = ex.replace("(", n * "(").replace(")", n * ")")
        assert QueryAst(ex_superflouous_parens, CONVERTERS).ast == q.ast

    # Test that we don't actually need parentheses around comparison expressions
    assert QueryAst("date eq '2016-05-01' AND (cost ge 20 OR cost lt 10.0)", CONVERTERS).ast == q.ast

    # Missing opening paren
    verify_bad_syntax_reported(ex[1:])

    # Missing closing paren
    verify_bad_syntax_reported(ex[:-1], "unexpected EOF while parsing")

    # Superflouous closing paren in the middle
    verify_bad_syntax_reported("(date eq '2016-05-01')) AND (cost gt 20)")
    return
