"""Seleção de arquivos por turno, arquivos fora do catálogo e datas do 2º turno (sem rede)."""

import re

import httpx
import pandas as pd

from tse import bq_raw, ckan, espelho, urna_logs

CDN = "https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026"


def _rec(urls):
    return pd.DataFrame({"dataset": "ds", "recurso": urls, "formato": "ZIP", "url": urls, "tamanho": None,
                         "modificado": None, "no_catalogo": True})


def _http(existentes):
    return httpx.Client(transport=httpx.MockTransport(
        lambda req: httpx.Response(200 if str(req.url) in existentes else 404)))


def test_fora_do_catalogo_uf_ausente_com_timestamp_dos_irmaos():
    urls = [f"{CDN}/buweb/bweb_2t_{uf}_261020260742.zip" for uf in ckan.UFS if uf != "RR"]
    rr = f"{CDN}/buweb/bweb_2t_RR_261020260742.zip"
    novos = ckan.fora_do_catalogo(_rec(urls), 2, _http({rr, rr + ".sha512"}))
    assert list(novos["url"]) == [rr, rr + ".sha512"]
    assert not novos["no_catalogo"].any()


def test_fora_do_catalogo_deriva_do_1o_turno_quando_o_turno_nao_esta_listado():
    urls = [f"{CDN}/arqurnatot/bu_imgbu_logjez_rdv_vscmr_2026_1t_{uf}.zip" for uf in ckan.UFS]
    existentes = {u.replace("_1t_", "_2t_") for u in urls if "_SP." not in u}
    novos = ckan.fora_do_catalogo(_rec(urls), 2, _http(existentes))
    assert set(novos["url"]) == existentes  # SP não respondeu 200 e fica de fora


def test_fora_do_catalogo_nada_a_fazer():
    urls = [f"{CDN}/odsele/votacao_secao/votacao_secao_2026_{uf}.zip" for uf in ckan.UFS]
    assert ckan.fora_do_catalogo(_rec(urls), 2, _http(set())).empty


def test_do_turno():
    urls = pd.Series(["x/bweb_1t_AC_1.zip", "x/bweb_2t_AC_1.zip", "x/votacao_secao_2026_AC.zip",
                      "x/bu_imgbu_logjez_rdv_vscmr_2026_2t_AC.zip"])
    assert list(espelho.do_turno(urls, 2)) == [False, True, True, True]
    assert list(espelho.do_turno(urls, None)) == [True] * 4


def test_mudou_no_servidor():
    anterior = {"bytes": "100", "baixado_em": "2026-10-14T11:02:23+00:00"}
    assert not espelho.mudou_no_servidor(anterior, 100, "Mon, 05 Oct 2026 10:00:00 GMT")
    assert espelho.mudou_no_servidor(anterior, 100, "Mon, 26 Oct 2026 17:42:32 GMT")
    assert espelho.mudou_no_servidor(anterior, 101, None)


def test_tabelas_do_2o_turno():
    def tabela(nome):
        return next(t for t, p in bq_raw.TABELAS_CSV.items() if re.match(p, nome))

    assert tabela("bweb_2t_ac_261020260742.csv") == "boletim_urna_2t"
    assert tabela("bweb_1t_ac_051020261403.csv") == "boletim_urna"
    assert tabela("csec_2t_zz_251020261345.csv") == "correspondencia_secao_2t"
    assert tabela("votacao_secao_2026_ac.csv") == "votacao_secao"
    assert bq_raw.RE_UF_GEDAI.search("log_gedai_2t_ZZ_251020261327.zip").group(1) == "ZZ"


def _log(dia, eventos):
    return "\n".join(f"{dia} {h}\tINFO\t0\tVOTA\t{m}\tHASH" for h, m in eventos)


def test_secao_do_2o_turno_usa_o_dia_e_o_corte_de_25_10():
    voto = ["Aguardando digitação do identificador", "Tipo de habilitação do eleitor [biométrica]",
            "O voto do eleitor foi computado"]
    eventos = [("06:00:01", "Urna pronta para receber votos")]  # Acre: fuso -2
    eventos += [("10:00:00", m) for m in voto] + [("15:10:00", m) for m in voto]  # 12h e 17h10 de Brasília
    nome = "o03221ac0101500020088-log.jez"
    linha, tardios = urna_logs.variaveis_secao(nome, [_log("25/10/2026", eventos)], "AC", turno=2)
    assert linha["fuso_inferido"] == -2
    assert (linha["votos_antes_17"], linha["votos_apos_17"]) == (1, 1)
    assert len(tardios) == 1
    # o mesmo log lido como 1º turno não tem nenhum evento do dia 04/10
    assert urna_logs.variaveis_secao(nome, [_log("25/10/2026", eventos)], "AC", turno=1)[0]["n_votos"] == 0


def _log_app(dia, eventos):
    return "\n".join(f"{dia} {h}\tINFO\t0\t{app}\t{m}\tHASH" for h, app, m in eventos)


def _config(h, mun, zona, secao):
    return [(h, "GAP", f"Município: {mun}"), (h, "GAP", f"Zona Eleitoral: {zona}"), (h, "GAP", f"Seção Eleitoral: {secao}")]


def test_log_configurado_para_outra_secao_fica_fora_da_contagem():
    voto = [("10:00:00", "VOTA", "Aguardando digitação do identificador"),
            ("10:00:05", "VOTA", "Voto confirmado para [Presidente]"), ("10:00:06", "VOTA", "O voto do eleitor foi computado")]
    propria = _log_app("25/10/2026", _config("07:00:00", "57932", "0009", "0085") + voto)
    outra = _log_app("25/10/2026", _config("07:00:00", "57932", "0009", "0112") + voto)
    contingencia = _log_app("25/10/2026", _config("09:00:00", "57932", "0009", "0000")
                            + _config("09:05:00", "57932", "0009", "0085") + [(h.replace("10:", "11:"), a, m) for h, a, m in voto])
    linha, _ = urna_logs.variaveis_secao("o03221es5793200090085-log.jez", [propria, outra, contingencia], "ES", turno=2)
    assert (linha["n_votos"], linha["n_logs"], linha["n_logs_outra_secao"]) == (2, 2, 1)


def test_voto_confirmado_e_interrompido_por_queda_de_energia_conta():
    eventos = [("08:00:01", "VOTA", "Urna pronta para receber votos"),
               ("08:48:50", "VOTA", "Aguardando digitação do identificador"),
               ("08:48:55", "VOTA", "Tipo de habilitação do eleitor [biométrica]"),
               ("08:49:04", "VOTA", "Voto confirmado para [Presidente]"),
               ("09:03:46", "LOGD", "Início das operações do logd"),  # urna religou sem gravar "computado"
               ("09:10:00", "VOTA", "Aguardando digitação do identificador"),
               ("09:10:05", "VOTA", "Voto confirmado para [Governador]"),  # não chegou ao último cargo
               ("09:12:00", "VOTA", "Aguardando digitação do identificador"),
               ("09:12:05", "VOTA", "Voto confirmado para [Presidente]"),
               ("09:12:06", "VOTA", "O voto do eleitor foi computado"),
               ("09:20:00", "VOTA", "Aguardando digitação do identificador"),
               ("09:20:05", "VOTA", "Voto confirmado para [Presidente]")]  # log termina aqui
    linha, _ = urna_logs.variaveis_secao("o03221ba3471100210178-log.jez", [_log_app("25/10/2026", eventos)], "BA", turno=2)
    assert (linha["n_votos"], linha["n_votos_interrompidos"], linha["n_biometrica"]) == (3, 2, 1)
