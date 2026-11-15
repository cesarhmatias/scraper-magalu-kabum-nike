from __future__ import annotations

from datetime import datetime, timezone

from openpyxl import load_workbook

from anuncios.config import Config
from anuncios.coletor import Coleta
from anuncios.export import gerar_planilha
from anuncios.models import Anuncio, ResultadoDominio


def _anuncio(dominio="magazineluiza.com.br", titulo="Tênis de Corrida Swift 5"):
    return Anuncio(
        dominio=dominio, termo="tênis de corrida", pagina=1, posicao=1, id="bk1",
        titulo=titulo, marca="Olympikus", preco=229.9, preco_original=349.9,
        desconto_pct=34, parcelamento="3x de R$ 76,63 sem juros", vendedor="Loja",
        categoria="Esporte e Lazer", preco_pix=202.31, disponivel=True,
        avaliacao=4.77, avaliacoes=159, patrocinado=None,
        url="https://www.magazineluiza.com.br/produto/1/",
        imagem="https://exemplo/img.jpg",
        coletado_em=datetime(2026, 11, 15, 0, 30, tzinfo=timezone.utc),
        transporte="h3", fonte="https://exemplo/fonte",
    )


def test_gera_planilha_com_abertura_e_resumo(tmp_path):
    coleta = Coleta(termo="tênis de corrida")
    resultado = ResultadoDominio(
        dominio="magazineluiza.com.br", termo="tênis de corrida", anuncios=[_anuncio()],
        paginas=1, total_declarado=10000, transporte="h3", duracao_ms=1200,
    )
    coleta.resultados.append(resultado)
    coleta.falhas.append(ResultadoDominio(dominio="nike.com.br", termo="tênis de corrida",
                                          erros=["bloqueio: access denied"]))
    caminho = tmp_path / "saida.xlsx"
    gerar_planilha(coleta, caminho, Config(proxy=None))
    assert caminho.exists() and caminho.stat().st_size > 4000

    wb = load_workbook(caminho)
    assert wb.sheetnames == ["Anúncios", "Resumo"]
    ws = wb["Anúncios"]
    assert ws.max_row == 2
    cabecalho = [c.value for c in ws[1]]
    assert "Preço (R$)" in cabecalho and "Preço Pix (R$)" in cabecalho
    assert ws["A2"].value == "magazineluiza.com.br"
    assert ws["B2"].value == "tênis de corrida"
    assert ws["F2"].value == "Tênis de Corrida Swift 5"
    assert ws["H2"].value == 229.9
    assert ws["U2"].value == "h3"
    assert ws["V2"].value == datetime(2026, 11, 15, 0, 30)  # sem tzinfo no Excel

    resumo = wb["Resumo"]
    valores = {row[0]: row[1] for row in resumo.iter_rows(values_only=True) if row[0]}
    assert valores["Termo"] == "tênis de corrida"
    assert valores["Anúncios"] == 1
    assert valores["Domínios com falha"] == 1
