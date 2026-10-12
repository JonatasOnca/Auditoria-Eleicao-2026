"""Cliente da API oficial de Resultados do TSE (https://resultados.tse.jus.br).

É a mesma API usada pelo app/site "Resultados" do TSE. Os endpoints foram
extraídos do bundle JavaScript do app em 2026-10-12 (ver docs/api_resultados.md).

Assim como o app oficial, cada arquivo é lido na versão assinada (`.jws`,
JWS compacto EdDSA/Ed25519) e só é aceito se a assinatura do TSE for válida.
Cada leitura fica registrada em `ResultadosTSE.registro` (URL, SHA-256 do token,
data de geração do TSE, resultado da verificação) para preservar a cadeia de
custódia. Se `snapshot_dir` for informado, os tokens `.jws` originais são gravados
em disco e podem ser verificados de forma independente por terceiros.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

HOST = "https://resultados.tse.jus.br"
USER_AGENT = "Auditoria-Eleicao-2026/0.1 (pesquisa; dados publicos TSE)"

# Chave pública de assinatura do ambiente "prod", embutida no app oficial (v26.10.9)
# e publicada em TSE_JWK_URL.
TSE_JWK_PROD = {
    "kty": "OKP",
    "use": "sig",
    "key_ops": ["verify"],
    "alg": "EdDSA",
    "kid": "sNbt9Q_fLS65zE1_ZLNV-XRRwPY",
    "crv": "Ed25519",
    "x": "kWlpNHjuws1csyQZwzn3Fhzbi3RD435RbpThtSr4hMc",
}
TSE_JWK_URL = f"{HOST}/oficial/app/assets/assinatura-jws/prod.jwk.json"

CARGOS = {
    1: "Presidente",
    3: "Governador",
    5: "Senador",
    6: "Deputado Federal",
    7: "Deputado Estadual",
    8: "Deputado Distrital",
}

# Códigos de eleição do ciclo 2026 (fonte: /oficial/comum/config/ele-c.json)
ELEICAO_FEDERAL_T1 = 6257
ELEICAO_FEDERAL_T2 = 6258
ELEICAO_ESTADUAL_T1 = 6259
ELEICAO_ESTADUAL_T2 = 6260


def eleicao_do_cargo(cargo: int, turno: int = 1) -> int:
    """Presidente é eleição federal; os demais cargos são da eleição estadual."""
    if cargo == 1:
        return ELEICAO_FEDERAL_T1 if turno == 1 else ELEICAO_FEDERAL_T2
    return ELEICAO_ESTADUAL_T1 if turno == 1 else ELEICAO_ESTADUAL_T2


def _num(valor: str | None) -> float | None:
    """Os números da API vêm como string, com vírgula decimal."""
    if valor in (None, ""):
        return None
    return float(str(valor).replace(",", "."))


def _int(valor: str | None) -> int | None:
    return None if valor in (None, "") else int(valor)


def _b64url(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


class AssinaturaInvalida(Exception):
    """O arquivo não tem assinatura válida do TSE; os dados não devem ser usados."""


def verificar_jws(token: str, jwk: dict = TSE_JWK_PROD) -> tuple[dict, dict]:
    """Verifica um JWS compacto EdDSA e devolve (cabeçalho, payload JSON)."""
    partes = token.strip().split(".")
    if len(partes) != 3:
        raise AssinaturaInvalida("JWS malformado (esperado header.payload.assinatura)")
    h, p, sig = partes
    try:
        cabecalho = json.loads(_b64url(h))
    except ValueError as e:
        raise AssinaturaInvalida(f"Cabeçalho JWS ilegível: {e}") from e
    if cabecalho.get("alg") != "EdDSA" or cabecalho.get("kid") != jwk["kid"]:
        raise AssinaturaInvalida(f"Cabeçalho inesperado: {cabecalho}")
    chave = Ed25519PublicKey.from_public_bytes(_b64url(jwk["x"]))
    try:
        chave.verify(_b64url(sig), f"{h}.{p}".encode())
    except InvalidSignature as e:
        raise AssinaturaInvalida("Assinatura Ed25519 não confere") from e
    return cabecalho, json.loads(_b64url(p))


@dataclass
class Leitura:
    url: str
    sha256: str
    bytes: int
    lido_em: str
    gerado_tse: str | None  # data/hora de geração informada pelo TSE (dg + hg)
    assinatura_ok: bool
    kid: str | None


class ResultadosTSE:
    def __init__(
        self,
        ciclo: str = "ele2026",
        ambiente: str = "oficial",
        max_conexoes: int = 4,
        timeout: float = 30.0,
        snapshot_dir: str | Path | None = None,
        verificar_assinatura: bool = True,
    ):
        self.ciclo = ciclo
        self.base = f"{HOST}/{ambiente}"
        self.max_conexoes = max_conexoes
        self.snapshot_dir = Path(snapshot_dir) if snapshot_dir else None
        self.registro: list[Leitura] = []
        self._cache: dict[str, dict] = {}
        self._http = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            limits=httpx.Limits(max_connections=max_conexoes),
            transport=httpx.HTTPTransport(retries=3),
        )
        self.verificar_assinatura = verificar_assinatura
        self.jwk = TSE_JWK_PROD
        if verificar_assinatura:
            self._conferir_chave_publicada()

    def _conferir_chave_publicada(self) -> None:
        """Detecta rotação de chave: se a chave publicada mudou, usa a publicada e avisa."""
        try:
            publicada = self._http.get(TSE_JWK_URL).raise_for_status().json()
        except (httpx.HTTPError, ValueError) as e:
            warnings.warn(f"Não foi possível ler {TSE_JWK_URL} ({e}); usando a chave embutida.")
            return
        if {k: publicada.get(k) for k in ("kid", "x")} != {k: TSE_JWK_PROD[k] for k in ("kid", "x")}:
            warnings.warn(f"Chave JWS publicada pelo TSE difere da embutida; usando a publicada: {publicada}")
            self.jwk = publicada

    # ------------------------------------------------------------------ HTTP

    def _get_json(self, caminho: str) -> dict:
        if self.verificar_assinatura:
            caminho = caminho.removesuffix(".json") + ".jws"
        url = f"{self.base}/{caminho}"
        if url in self._cache:
            return self._cache[url]
        # o app oficial também anexa nocache para não receber cópias velhas do CDN
        resp = self._http.get(url, params={"nocache": int(time.time() * 1000)})
        resp.raise_for_status()
        conteudo = resp.content
        kid = None
        if self.verificar_assinatura:
            cabecalho, dados = verificar_jws(conteudo.decode("ascii"), self.jwk)
            kid = cabecalho["kid"]
        else:
            dados = json.loads(conteudo)
        sha = hashlib.sha256(conteudo).hexdigest()
        gerado = f"{dados.get('dg')} {dados.get('hg')}" if isinstance(dados, dict) and "dg" in dados else None
        self.registro.append(
            Leitura(url, sha, len(conteudo), datetime.now(timezone.utc).isoformat(), gerado,
                    self.verificar_assinatura, kid)
        )
        if self.snapshot_dir:
            destino = self.snapshot_dir / caminho
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(conteudo)
        self._cache[url] = dados
        return dados

    def registro_df(self) -> pd.DataFrame:
        return pd.DataFrame([vars(l) for l in self.registro])

    # ---------------------------------------------------------- Configuração

    def eleicoes(self) -> pd.DataFrame:
        """Todas as eleições publicadas na API (todos os ciclos)."""
        dados = self._get_json("comum/config/ele-c.json")
        linhas = []
        for pleito in dados["pl"]:
            for e in pleito["e"]:
                linhas.append(
                    {
                        "ciclo": pleito["c"],
                        "pleito": pleito["cd"],
                        "data": pleito["dt"],
                        "eleicao": int(e["cd"]),
                        "nome": e["nm"],
                        "turno": int(e["t"]),
                        "eleicao_2t": e.get("cdt2") or None,
                    }
                )
        return pd.DataFrame(linhas)

    def municipios(self, eleicao: int = ELEICAO_FEDERAL_T1) -> pd.DataFrame:
        """UFs, municípios (código TSE e IBGE) e zonas de uma eleição."""
        dados = self._get_json(f"{self.ciclo}/{eleicao}/config/mun-e{eleicao:06d}-cm.json")
        linhas = [
            {
                "uf": abr["cd"].upper(),
                "uf_nome": abr["ds"],
                "cd_municipio": mu["cd"],
                "cd_ibge": mu.get("cdi") or None,
                "municipio": mu["nm"],
                "capital": mu.get("c") == "s",
                "zonas": mu.get("z", []),
            }
            for abr in dados["abr"]
            for mu in abr["mu"]
        ]
        return pd.DataFrame(linhas)

    # -------------------------------------------------------------- Resultados

    def resultado_bruto(
        self,
        cargo: int,
        uf: str = "br",
        municipio: str | None = None,
        zona: str | None = None,
        eleicao: int | None = None,
    ) -> dict:
        """JSON "unificado" (-u.json) de um cargo numa abrangência.

        uf="br" é o total nacional (só presidente); uf="zz" é o exterior.
        """
        eleicao = eleicao or eleicao_do_cargo(cargo)
        uf = uf.lower()
        mun = f"{int(municipio):05d}" if municipio else ""
        zon = f"-z{int(zona):04d}" if zona else ""
        arquivo = f"{uf}{mun}{zon}-c{cargo:04d}-e{eleicao:06d}-u.json"
        return self._get_json(f"{self.ciclo}/{eleicao}/dados/{uf}/{arquivo}")

    def totais(self, cargo: int, uf: str = "br", municipio: str | None = None,
               zona: str | None = None, eleicao: int | None = None) -> dict:
        """Seções, eleitorado, comparecimento, abstenção, brancos e nulos."""
        d = self.resultado_bruto(cargo, uf, municipio, zona, eleicao)
        s, e, v = d["s"], d["e"], d["v"]
        return {
            "eleicao": int(d["ele"]),
            "cargo": cargo,
            "uf": uf.upper(),
            "cd_municipio": municipio,
            "zona": zona,
            "gerado_tse": f"{d['dg']} {d['hg']}",
            "secoes_total": _int(s["ts"]),
            "secoes_totalizadas": _int(s["st"]),
            "pct_secoes_totalizadas": _num(s["pstn"]),
            "eleitorado": _int(e["te"]),
            "comparecimento": _int(e["c"]),
            "abstencao": _int(e["a"]),
            "pct_comparecimento": _num(e["pcn"]),
            "votos_totais": _int(v["tv"]),
            "votos_validos": _int(v["vv"]),
            "votos_nominais": _int(v["vnom"]),
            "votos_legenda": _int(v.get("van")),
            "brancos": _int(v["vb"]),
            "nulos": _int(v["tvn"]),
            "nulos_tecnicos": _int(v.get("vnt")),
            "pct_brancos": _num(v["pvbn"]),
            "pct_nulos": _num(v["ptvnn"]),
        }

    def candidatos(self, cargo: int, uf: str = "br", municipio: str | None = None,
                   zona: str | None = None, eleicao: int | None = None) -> pd.DataFrame:
        """Votação por candidato na abrangência (vazio para deputado no município)."""
        d = self.resultado_bruto(cargo, uf, municipio, zona, eleicao)
        linhas = []
        for carg in d.get("carg", []):
            for agr in carg.get("agr", []):
                for par in agr.get("par", []):
                    for c in par.get("cand", []):
                        linhas.append(
                            {
                                "uf": uf.upper(),
                                "cd_municipio": municipio,
                                "zona": zona,
                                "cargo": int(carg["cd"]),
                                "numero": c["n"],
                                "sq_candidato": c.get("sqcand"),
                                "nome_urna": c.get("nmu"),
                                "nome": c.get("nm"),
                                "partido": par.get("sg"),
                                "coligacao": agr.get("nm"),
                                "situacao_voto": c.get("dvt"),
                                "situacao": c.get("st"),
                                "eleito": c.get("e") == "s",
                                "votos": _int(c.get("vap")),
                                "pct_validos": _num(c.get("pvapn")),
                            }
                        )
        return pd.DataFrame(linhas).sort_values("votos", ascending=False, ignore_index=True) if linhas else pd.DataFrame()

    # ------------------------------------------------------ Varreduras em lote

    def _em_lote(self, func, argumentos: list[dict]) -> list:
        with ThreadPoolExecutor(max_workers=self.max_conexoes) as pool:
            return list(pool.map(lambda kw: func(**kw), argumentos))

    def totais_ufs(self, cargo: int, eleicao: int | None = None) -> pd.DataFrame:
        eleicao = eleicao or eleicao_do_cargo(cargo)
        ufs = sorted(self.municipios(eleicao)["uf"].unique())
        if cargo != 1:
            ufs = [u for u in ufs if u != "ZZ"]  # exterior só vota para presidente
        return pd.DataFrame(self._em_lote(self.totais, [{"cargo": cargo, "uf": u, "eleicao": eleicao} for u in ufs]))

    def totais_municipios(self, cargo: int, ufs: list[str] | None = None,
                          eleicao: int | None = None) -> pd.DataFrame:
        """Totais de todos os municípios (≈5.570 requisições para o Brasil inteiro)."""
        eleicao = eleicao or eleicao_do_cargo(cargo)
        mun = self.municipios(eleicao)
        if ufs:
            mun = mun[mun["uf"].isin([u.upper() for u in ufs])]
        args = [{"cargo": cargo, "uf": r.uf, "municipio": r.cd_municipio, "eleicao": eleicao}
                for r in mun.itertuples()]
        df = pd.DataFrame(self._em_lote(self.totais, args))
        return df.merge(mun[["cd_municipio", "cd_ibge", "municipio", "capital"]], on="cd_municipio", how="left")

    def candidatos_municipios(self, cargo: int, ufs: list[str] | None = None,
                              eleicao: int | None = None) -> pd.DataFrame:
        eleicao = eleicao or eleicao_do_cargo(cargo)
        mun = self.municipios(eleicao)
        if ufs:
            mun = mun[mun["uf"].isin([u.upper() for u in ufs])]
        args = [{"cargo": cargo, "uf": r.uf, "municipio": r.cd_municipio, "eleicao": eleicao}
                for r in mun.itertuples()]
        return pd.concat(self._em_lote(self.candidatos, args), ignore_index=True)

    def close(self) -> None:
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
