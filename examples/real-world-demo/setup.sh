#!/usr/bin/env bash
set -euo pipefail

python -m venv .venv-arrow-demo
. .venv-arrow-demo/bin/activate
python -m pip install --upgrade pip
python -m pip install 'arrow==0.12.1' pytest

cat > test_arrow_parser_error.py <<'PY'
import pytest
import arrow
from arrow.parser import ParserError


def test_invalid_multiformat_date_raises_parser_error():
    with pytest.raises(ParserError):
        arrow.get("20171017", ["YYYY.M.D"])
PY

python -m pytest test_arrow_parser_error.py -q
