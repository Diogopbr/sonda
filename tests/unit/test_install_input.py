from io import StringIO

import pytest

from scripts.install_user import read_credentials


def test_credentials_are_read_only_from_bounded_strict_json_stdin() -> None:
    credentials = read_credentials(
        StringIO(
            '{"email":"operador@example.com","name":"Operador","password":"senha longa de teste"}'
        )
    )
    assert credentials.email == "operador@example.com"
    assert "senha longa de teste" not in repr(credentials)


@pytest.mark.parametrize(
    "body",
    [
        "{",
        "[]",
        "{}",
        '{"email":1,"name":"Operador","password":"senha longa de teste"}',
        '{"email":"operador@example.com","name":"Operador","password":"curta"}',
        '{"email":"operador@example.com","name":"Operador",'
        '"password":"senha longa de teste","extra":1}',
        " " * 16385,
    ],
)
def test_invalid_installation_input_has_no_password_in_error(body: str) -> None:
    with pytest.raises(ValueError) as caught:
        read_credentials(StringIO(body))
    assert "senha longa de teste" not in str(caught.value)
