""" A parser for the query mini-language
The parser takes advantage of the fact that the query language is syntactically equivalent to a subset of Python's expression syntax, so
we convert qwuery strings to syntactically equivalent Python expressions, and use Python's parser to create their
abstract syntax trees

Specifically the query language has the following properties:
* Supported operators
  * Relational operators: EQ, NE, GT, LT, GE, LE
  * Logical operators: AND, OR and NOT
* Relational operators take a name on their left hand side, representing a database column, and a literal value on their right hand side
* Literal strings are either numbers (possibly negative and with a decimal point) or strings representing dates and times of day. The name on the
left-hand side of a relational operator determines the expected format of the literal value on the right-hand side.
* All operators, field-names and values are case-insensitive.
* As in SQL, C, Python etc., AND has higher precedences than OR. Parenthesis may be used to set any precedence.
"""

import re
import ast
import typing
import dataclasses
import operator


@dataclasses.dataclass
class Comparison:
    op: typing.Callable
    name: str
    value: typing.Any

@dataclasses.dataclass
class LogicalOperator:
    op: typing.Callable
    operands: typing.Sequence

class QueryAst:
    def __init__(self, query: str, field_value_converters: typing.Mapping[str, typing.Callable] = {}):
        self.query_text = query.strip()
        self.field_value_converters = field_value_converters      # TODO: Require this to be non-empty!
        self.ast = self._make_ast(self.query_text)

    PSEUDO_FILENAME = "<web request>"
    "Value that will be given as 'filename' when reporting syntax errors"

    _rel_ops_mapping = {
        "eq": "==",
        "ne": "!=",
        "gt": " >",
        "lt": " <",
        "ge": ">=",
        "le": "<=",
    }

    # Make sure we always substitute strings with strings of the same length, to get accurate error reporting
    assert(len(k) == len(v) for k, v in _rel_ops_mapping.items())

    _rel_op_re = re.compile("\\b({})\\b".format("|".join(_rel_ops_mapping)))

    def _make_ast(self, query: str) -> None:
        try:
            self.py_ast = ast.parse(self._query_to_python_expression(query), self.PSEUDO_FILENAME, mode="eval")
            try:
                root_node, = ast.iter_child_nodes(self.py_ast)
            except ValueError:
                self._raise_syntax_error("Multiple expressions or none. Exactly 1 expression is required", root_node)
            our_ast = self._parse_node(root_node)
        except SyntaxError as se:
            lines = query.splitlines()
            details = tuple(se.args[1])[:-1] + (lines[se.lineno - 1],)
            raise SyntaxError(se.args[0], details)

        return our_ast

    @classmethod
    def _query_to_python_expression(cls, query: str) -> str:
        parts = cls._rel_op_re.split(query.lower())
        parts_converted = ( cls._rel_ops_mapping.get(p, p) for p in parts )
        return "".join(parts_converted)

    def _parse_node(self, node):
        if isinstance(node, ast.Compare):
            return self._parse_comparison(node)
        elif isinstance(node, ast.BoolOp) or isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return self._parse_boolean_expression(node)
        else:
            self._raise_syntax_error("Unsupported expression", node)

    def _parse_boolean_expression(self, node):
        child_nodes = ast.iter_child_nodes(node)
        ast_op = next(child_nodes)
        if isinstance(ast_op, ast.And):
            op = operator.and_
        elif isinstance(ast_op, ast.Or):
            op = operator.or_
        elif isinstance(ast_op, ast.Not):
            op = operator.not_
        else:
            assert not f"Unrecognized logical operator: {ast_op}"

        operands = tuple(map(self._parse_node, child_nodes))
        return LogicalOperator(op, operands)

    def _parse_comparison(self, node) -> Comparison:
        assert isinstance(node, ast.Compare)
        name_node, ast_op, value_node = ast.iter_child_nodes(node)
        assert isinstance(name_node, ast.Name)

        value = self._parse_value_node(value_node)
        value_converter = self.field_value_converters.get(name_node.id)
        if value_converter is None:
            raise NameError(f"No such field '{name_node.id}'")
        converted_value = value_converter(value)

        try:
            op = self._convert_rel_op(ast_op, node)
        except (ValueError, TypeError) as e:
            raise e.__class__(f"Failed to apply converter to field '{name_node.id}'" )from e
        return Comparison(op, name_node.id, converted_value)

    @classmethod
    def _parse_value_node(cls, value_node):
        if isinstance(value_node, ast.Str):
            return value_node.s
        elif isinstance(value_node, ast.Num):
            return value_node.n
        elif isinstance(value_node, ast.UnaryOp) and isinstance(value_node.op, ast.USub):
            try:
                return - cls._parse_value_node(value_node.operand)
            except TypeError:
                cls._raise_syntax_error("Attempt to negate non-number", value_node)
        else:
            cls._raise_syntax_error("Value is not a number or a string", value_node)

    @classmethod
    def _convert_rel_op(cls, ast_op, node) -> typing.Callable:
        if isinstance(ast_op, ast.Eq):
            return operator.eq
        elif isinstance(ast_op, ast.NotEq):
            return operator.ne
        elif isinstance(ast_op, ast.Gt):
            return operator.gt
        elif isinstance(ast_op, ast.Lt):
            return operator.lt
        elif isinstance(ast_op, ast.GtE):
            return operator.ge
        elif isinstance(ast_op, ast.LtE):
            return operator.le

        op_name = ast_op.__class__.__name__.lower()
        cls._raise_syntax_error(f"Unknown comparison operator '{op_name}'", node)

    @classmethod
    def _raise_syntax_error(cls, message: str, node):
        raise SyntaxError(message,
            (cls.PSEUDO_FILENAME, getattr(node, "lineno", 1), getattr(node, "col_offset", 0), ""))
