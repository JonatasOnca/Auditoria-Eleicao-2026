"""Verificação da assinatura JWS do TSE (requer rede: lê um arquivo real da API)."""

import base64

import httpx
import pytest

from tse.resultados_api import HOST, USER_AGENT, AssinaturaInvalida, verificar_jws

URL = f"{HOST}/oficial/ele2026/6257/dados/br/br-c0001-e006257-u.jws"


@pytest.fixture(scope="module")
def token() -> str:
    return httpx.get(URL, headers={"User-Agent": USER_AGENT}, timeout=30).raise_for_status().text.strip()


def test_assinatura_valida(token):
    cabecalho, dados = verificar_jws(token)
    assert cabecalho["alg"] == "EdDSA"
    assert dados["ele"] == "6257"


def test_payload_adulterado_e_rejeitado(token):
    h, p, sig = token.split(".")
    payload = base64.urlsafe_b64decode(p + "=" * (-len(p) % 4))
    adulterado = payload.replace(b'"c" : "', b'"c" : "9', 1)  # infla o comparecimento
    assert adulterado != payload
    p2 = base64.urlsafe_b64encode(adulterado).rstrip(b"=").decode()
    with pytest.raises(AssinaturaInvalida):
        verificar_jws(f"{h}.{p2}.{sig}")


def test_assinatura_trocada_e_rejeitada(token):
    h, p, sig = token.split(".")
    sig2 = ("A" if sig[0] != "A" else "B") + sig[1:]
    with pytest.raises(AssinaturaInvalida):
        verificar_jws(f"{h}.{p}.{sig2}")
