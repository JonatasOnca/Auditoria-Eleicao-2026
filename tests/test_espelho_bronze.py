"""enviar_bronze nunca sobrescreve uma versão do bronze sem guardá-la (bucket falso em memória)."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from tse import bq_raw, espelho


class Blob:
    def __init__(self, bucket, name, dados=None, updated=None):
        self.bucket, self.name, self.dados = bucket, name, dados
        self.updated = updated or datetime(2026, 10, 14, 20, 18, 30, tzinfo=timezone.utc)

    @property
    def size(self):
        return len(self.dados)

    @property
    def crc32c(self):
        p = self.bucket.raiz / "_crc"
        p.write_bytes(self.dados)
        return espelho.crc32c_b64(p)

    def upload_from_filename(self, caminho, **_):
        self.dados = Path(caminho).read_bytes()
        self.bucket.objetos[self.name] = self
        self.bucket.envios += 1

    def reload(self):
        pass


class Bucket:
    name = "bronze-teste"

    def __init__(self, raiz):
        self.raiz, self.objetos, self.envios = raiz, {}, 0

    def get_blob(self, nome):
        return self.objetos.get(nome)

    def blob(self, nome):
        return self.objetos.get(nome) or Blob(self, nome)

    def copy_blob(self, blob, _bucket, novo_nome):
        self.objetos[novo_nome] = Blob(self, novo_nome, blob.dados, blob.updated)


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setattr(bq_raw, "retry_gcs", lambda: None)
    local = tmp_path / "votacao_secao_2026_AC.zip"
    local.write_bytes(b"versao nova com os dois turnos")
    return Bucket(tmp_path), local


def test_objeto_ausente_e_enviado(ambiente):
    bucket, local = ambiente
    uri = espelho.enviar_bronze(bucket, local, "resultados-2026")
    assert uri == "gs://bronze-teste/tse/zip/resultados-2026/votacao_secao_2026_AC.zip"
    assert bucket.envios == 1 and list(bucket.objetos) == ["tse/zip/resultados-2026/votacao_secao_2026_AC.zip"]


def test_objeto_identico_nao_e_reenviado(ambiente):
    bucket, local = ambiente
    nome = "tse/zip/resultados-2026/votacao_secao_2026_AC.zip"
    bucket.objetos[nome] = Blob(bucket, nome, local.read_bytes())
    espelho.enviar_bronze(bucket, local, "resultados-2026")
    assert bucket.envios == 0 and list(bucket.objetos) == [nome]


def test_objeto_diferente_e_preservado_antes_de_substituir(ambiente):
    bucket, local = ambiente
    nome = "tse/zip/resultados-2026/votacao_secao_2026_AC.zip"
    bucket.objetos[nome] = Blob(bucket, nome, b"versao de 14/10 so com o 1o turno")
    espelho.enviar_bronze(bucket, local, "resultados-2026")
    antigo = "tse/zip/resultados-2026/_substituidos/20261014T201830/votacao_secao_2026_AC.zip"
    assert bucket.objetos[antigo].dados == b"versao de 14/10 so com o 1o turno"
    assert bucket.objetos[nome].dados == local.read_bytes() and bucket.envios == 1


def test_marca_do_manifesto_tem_precedencia(ambiente):
    bucket, local = ambiente
    nome = "tse/zip/resultados-2026/votacao_secao_2026_AC.zip"
    bucket.objetos[nome] = Blob(bucket, nome, b"versao antiga")
    espelho.enviar_bronze(bucket, local, "resultados-2026", substituido="20261014T110213")
    assert "tse/zip/resultados-2026/_substituidos/20261014T110213/votacao_secao_2026_AC.zip" in bucket.objetos
