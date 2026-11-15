"""Geracao da planilha XLSX com os anuncios e o resumo da coleta."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from .config import Config
from .coletor import Coleta

CABECALHO = [
    ("dominio", "Domínio", 22),
    ("termo", "Termo", 24),
    ("pagina", "Página", 8),
    ("posicao", "Posição", 9),
    ("id", "ID", 14),
    ("titulo", "Título", 60),
    ("marca", "Marca", 16),
    ("preco", "Preço (R$)", 14),
    ("preco_original", "Preço original (R$)", 18),
    ("desconto_pct", "Desconto (%)", 12),
    ("parcelamento", "Parcelamento", 24),
    ("vendedor", "Vendedor", 22),
    ("categoria", "Categoria", 20),
    ("preco_pix", "Preço Pix (R$)", 14),
    ("disponivel", "Disponível", 11),
    ("avaliacao", "Avaliação", 10),
    ("avaliacoes", "Avaliações", 11),
    ("patrocinado", "Patrocinado", 12),
    ("url", "URL", 60),
    ("imagem", "Imagem", 45),
    ("transporte", "Transporte", 11),
    ("coletado_em", "Coletado em", 19),
    ("fonte", "Fonte", 45),
]

_AZUL = "1F3864"
_ZEBRA = "EEF3FA"
_BORDA = Border(bottom=Side(style="thin", color="D0D7E5"))


def _estilizar_cabecalho(ws, colunas: int) -> None:
    for c in range(1, colunas + 1):
        celula = ws.cell(row=1, column=c)
        celula.font = Font(bold=True, color="FFFFFF", size=11)
        celula.fill = PatternFill("solid", fgColor=_AZUL)
        celula.alignment = Alignment(vertical="center", horizontal="left", wrap_text=True)
    ws.row_dimensions[1].height = 28
    ws.freeze_panes = "A2"


def gerar_planilha(coleta: Coleta, caminho: str | Path, cfg: Config) -> Path:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Anúncios"

    for i, (chave, titulo, largura) in enumerate(CABECALHO, start=1):
        ws.cell(row=1, column=i, value=titulo)
        ws.column_dimensions[get_column_letter(i)].width = largura
    _estilizar_cabecalho(ws, len(CABECALHO))

    linha = 2
    for resultado in coleta.resultados:
        for a in resultado.anuncios:
            valores = {
                "dominio": a.dominio,
                "termo": a.termo,
                "pagina": a.pagina,
                "posicao": a.posicao,
                "id": a.id,
                "titulo": a.titulo,
                "marca": a.marca,
                "preco": a.preco,
                "preco_original": a.preco_original,
                "desconto_pct": a.desconto_pct,
                "parcelamento": a.parcelamento,
                "vendedor": a.vendedor,
                "categoria": a.categoria,
                "preco_pix": a.preco_pix,
                "disponivel": a.disponivel,
                "avaliacao": a.avaliacao,
                "avaliacoes": a.avaliacoes,
                "patrocinado": a.patrocinado,
                "url": a.url,
                "imagem": a.imagem,
                "transporte": a.transporte,
                "coletado_em": a.coletado_em,
                "fonte": a.fonte,
            }
            for col, (chave, _titulo, _largura) in enumerate(CABECALHO, start=1):
                valor = valores.get(chave)
                if chave == "coletado_em" and hasattr(valor, "tzinfo") and valor.tzinfo is not None:
                    valor = valor.replace(tzinfo=None)
                celula = ws.cell(row=linha, column=col, value=valor)
                celula.border = _BORDA
                if linha % 2 == 0:
                    celula.fill = PatternFill("solid", fgColor=_ZEBRA)
                if chave in {"preco", "preco_original", "preco_pix"} and celula.value is not None:
                    celula.number_format = 'R$ #,##0.00'
                elif chave == "coletado_em":
                    celula.number_format = "dd/mm/yyyy hh:mm"
                elif chave == "url" and celula.value:
                    celula.hyperlink = str(celula.value)
                    celula.font = Font(color="0563C1", underline="single")
                    celula.alignment = Alignment(vertical="top", wrap_text=False)
                elif chave == "titulo":
                    celula.alignment = Alignment(vertical="top", wrap_text=True)
            linha += 1

    if linha > 2:
        tabela = Table(displayName="Anuncios", ref=f"A1:{get_column_letter(len(CABECALHO))}{linha - 1}")
        tabela.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2", showRowStripes=False, showColumnStripes=False
        )
        ws.add_table(tabela)
    else:
        ws.cell(row=2, column=1, value="Nenhum anúncio coletado.")

    # -- resumo ------------------------------------------------------------
    rs = wb.create_sheet("Resumo")
    rs.column_dimensions["A"].width = 30
    rs.column_dimensions["B"].width = 90
    rs["A1"] = "Coleta de anúncios"
    rs["A1"].font = Font(bold=True, size=14, color=_AZUL)
    metadados = [
        ("Termo", coleta.termo),
        ("Anúncios", len(coleta.anuncios)),
        ("Domínios com resultado", len([r for r in coleta.resultados if r.anuncios])),
        ("Domínios com falha", len(coleta.falhas)),
        ("Duração total (ms)", coleta.duracao_ms),
        ("Transporte", cfg.transporte),
        ("Proxy", cfg.proxy_descricao),
        ("Gerado em", datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M:%S UTC")),
    ]
    for i, (rotulo, valor) in enumerate(metadados, start=3):
        rs.cell(row=i, column=1, value=rotulo).font = Font(bold=True)
        rs.cell(row=i, column=2, value=valor)

    linha = len(metadados) + 5
    titulos = ["Domínio", "Anúncios", "Páginas", "Total declarado", "Transporte", "Build/ID", "Duração (ms)", "Erros", "Avisos"]
    for c, titulo in enumerate(titulos, start=1):
        celula = rs.cell(row=linha, column=c, value=titulo)
        celula.font = Font(bold=True, color="FFFFFF")
        celula.fill = PatternFill("solid", fgColor=_AZUL)
    for resultado in [*coleta.resultados, *coleta.falhas]:
        linha += 1
        valores = [
            resultado.dominio,
            len(resultado.anuncios),
            resultado.paginas,
            resultado.total_declarado,
            resultado.transporte,
            resultado.build_id or "",
            resultado.duracao_ms,
            "; ".join(resultado.erros),
            "; ".join(resultado.avisos),
        ]
        for c, valor in enumerate(valores, start=1):
            rs.cell(row=linha, column=c, value=valor).alignment = Alignment(vertical="top", wrap_text=(c >= 8))
    for c, largura in enumerate([24, 10, 10, 15, 12, 32, 13, 60, 50], start=1):
        rs.column_dimensions[get_column_letter(c)].width = largura
    rs.freeze_panes = rs.cell(row=len(metadados) + 6, column=1)

    wb.save(caminho)
    return caminho
