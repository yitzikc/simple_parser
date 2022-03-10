# Meal-Log Query Language

All meal-log endpoints that may return multiple meal results support querying using a dedicated mini-language to limit the results withing what the
endpoint would otherwise give. The query is optional, and may be supplied either via the URL or by passing JSON content in the GET request.
Specifying an empty query is equivalent to not specifying one at all. Malfromed queries return HTTP error code 400 and a JSON object whose
_message_ field describes the problem. The error description message may contain multiple lines, and is optimized for displaying using a fixed font.

## Language Description

Queries are made of one of more comparison expression, joined by logical operators. Comparison expressions are
in the format:

    field operator [number|string]

The comparison operators are the 6 usual ones: `EQ, NE, GT, LT, GE, LE`. They may also be represented
in the form used by languages like C, as `==. !=, >, <, >=, <=` respetively. Numbers may optionally
include a decimal point and a minus sign. Strings may be delimited using either single or double quotes.

The logical operators are the 3 expected ones, in order of precedence from the highest to the lower:

* `NOT`
* `AND`
* `OR`

Parenthesis may be used to group expressions and set the evaluation order explicitly.

All operators, field-names and values are case-insensitive.

The following fields are supported:

* _calories_: a positive number (possibly with a decimal point)
* _date_: a string givint the date in ISO format, e.g. `2019-08-01`
* _time_of_day_: Can be given either as a string in 'hh:mm:ss' format, or as a number in _hhmmss_ format, e.g. '09:27:01' or 092701. When using a number,
the leading 0 is optional.

## Example queries

```SQL
 date eq '2016-05-01' AND (number_of_calories gt 20 OR number_of_calories le 10.5)
 ```

The same query with C-style operators and lowercase keywords:

```python
 date == '2016-05-01' and (number_of_calories > 20 or number_of_calories <= 10.5)
 ```
