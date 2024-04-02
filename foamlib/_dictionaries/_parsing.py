from typing import Mapping, MutableMapping, Optional, Sequence, Tuple

from pyparsing import (
    Dict,
    Forward,
    Group,
    Keyword,
    LineEnd,
    Literal,
    Located,
    Opt,
    ParseResults,
    ParserElement,
    QuotedString,
    Word,
    c_style_comment,
    common,
    cpp_style_comment,
    identbodychars,
    printables,
)

from ._base import FoamDictionaryBase

_YES = Keyword("yes").set_parse_action(lambda: True)
_NO = Keyword("no").set_parse_action(lambda: False)
_DIMENSIONS = (
    Literal("[").suppress() + common.number * 7 + Literal("]").suppress()
).set_parse_action(lambda tks: FoamDictionaryBase.DimensionSet(*tks))


def _list_of(elem: ParserElement) -> ParserElement:
    return Opt(
        Literal("List") + Literal("<") + common.identifier + Literal(">")
    ).suppress() + (
        (
            Opt(common.integer).suppress()
            + (
                Literal("(").suppress()
                + Group((elem)[...], aslist=True)
                + Literal(")").suppress()
            )
        )
        | (
            common.integer + Literal("{").suppress() + elem + Literal("}").suppress()
        ).set_parse_action(lambda tks: [[tks[1]] * tks[0]])
    )


_TENSOR = _list_of(common.number) | common.number
_IDENTIFIER = Word(identbodychars + "$", printables.replace(";", ""))
_DIMENSIONED = (Opt(_IDENTIFIER) + _DIMENSIONS + _TENSOR).set_parse_action(
    lambda tks: FoamDictionaryBase.Dimensioned(*reversed(tks.as_list()))
)
_FIELD = (Keyword("uniform").suppress() + _TENSOR) | (
    Keyword("nonuniform").suppress() + _list_of(_TENSOR)
)
_TOKEN = QuotedString('"', unquote_results=False) | _IDENTIFIER
_ITEM = Forward()
_LIST = _list_of(_ITEM)
_ITEM <<= (
    _FIELD | _LIST | _DIMENSIONED | _DIMENSIONS | common.number | _YES | _NO | _TOKEN
)
_TOKENS = (
    QuotedString('"', unquote_results=False) | Word(printables.replace(";", ""))
)[2, ...].set_parse_action(lambda tks: " ".join(tks))

_VALUE = _ITEM ^ _TOKENS

_ENTRY = Forward()
_DICTIONARY = Dict(Group(_ENTRY)[...])
_ENTRY <<= Located(
    _TOKEN
    + (
        (Literal("{").suppress() + _DICTIONARY + Literal("}").suppress())
        | (Opt(_VALUE, default="") + Literal(";").suppress())
    )
)
_FILE = (
    _DICTIONARY.ignore(c_style_comment)
    .ignore(cpp_style_comment)
    .ignore(Literal("#include") + ... + LineEnd())  # type: ignore [no-untyped-call]
)


def _flatten_result(
    parse_result: ParseResults, *, _keywords: Sequence[str] = ()
) -> Mapping[Sequence[str], Tuple[int, Optional[FoamDictionaryBase.Value], int]]:
    ret: MutableMapping[
        Sequence[str], Tuple[int, Optional[FoamDictionaryBase.Value], int]
    ] = {}
    start = parse_result.locn_start
    assert isinstance(start, int)
    item = parse_result.value
    assert isinstance(item, Sequence)
    end = parse_result.locn_end
    assert isinstance(end, int)
    key, *values = item
    assert isinstance(key, str)
    ret[(*_keywords, key)] = (start, None, end)
    for value in values:
        if isinstance(value, ParseResults):
            ret.update(_flatten_result(value, _keywords=(*_keywords, key)))
        else:
            ret[(*_keywords, key)] = (start, value, end)
    return ret


def parse(
    contents: str,
) -> Mapping[Sequence[str], Tuple[int, Optional[FoamDictionaryBase.Value], int]]:
    parse_results = _FILE.parse_string(contents, parse_all=True)
    ret: MutableMapping[
        Sequence[str], Tuple[int, Optional[FoamDictionaryBase.Value], int]
    ] = {}
    for parse_result in parse_results:
        ret.update(_flatten_result(parse_result))
    return ret


def entry_locn(
    parsed: Mapping[Sequence[str], Tuple[int, Optional[FoamDictionaryBase.Value], int]],
    keywords: Tuple[str, ...],
) -> Tuple[int, int]:
    """
    Location of an entry or where it should be inserted.
    """
    try:
        start, _, end = parsed[keywords]
    except KeyError:
        if len(keywords) > 1:
            _, _, end = parsed[keywords[:-1]]
            end -= 1
        else:
            end = -1

        start = end

    return start, end
