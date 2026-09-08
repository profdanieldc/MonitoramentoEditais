"""Coletor da SECTI-MA (secti.ma.gov.br).

A página de editais é uma lista por ano. Cada edital aparece como um
título — geralmente numerado, do tipo "1 - SELEÇÃO DE BOLSISTAS PARA
PROGRAMAS DE INOVAÇÃO" — seguido dos PDFs daquele processo: o edital em
si, retificações, erratas e listas de aprovados.

O parser percorre a seção de conteúdo na ordem em que ela aparece, em vez
de depender de classes CSS. Assim funciona tanto se os títulos forem <p>
quanto <h3> ou <strong>, e sobrevive a mudanças cosméticas de layout.

O prazo não existe no HTML: está dentro do PDF do edital. Como as janelas
da SECTI são curtas (houve edital com três dias entre abertura e
encerramento), vale o custo de abrir o arquivo.
"""

from __future__ import annotations

import re
import time
from datetime import date
from urllib.parse import urljoin

from coletores.base import (
    FonteIndisponivel, baixar_pdf, buscar, extrair_prazo, normalizar_url,
)
from nucleo.modelo import Edital, id_de

# Rótulos que identificam o documento principal, e não um anexo posterior.
PADRAO_EDITAL = re.compile(
    r"^\s*(?:\d+\s*[-–—]\s*)?(?:edital|chamada|processo\s+seletivo|"
    r"credenciamento|sele[çc][ãa]o)\b", re.IGNORECASE)

# Anexos que são desdobramento administrativo, não oportunidade nova.
PADRAO_ANEXO = re.compile(
    r"lista\s+(?:parcial|final)|resultado|classificad|aprovad|convoca|"
    r"homologa", re.IGNORECASE)


def urls_do_ano(base: str, hoje_: date | None = None) -> list[str]:
    """Monta as URLs a consultar.

    A SECTI mantém uma página por ano. Deixar o ano fixo no arquivo de
    configuração faria a coleta ler a página velha em silêncio a partir de
    1º de janeiro — falha sem erro, a pior espécie. Então o ano é
    calculado, e nos primeiros meses o ano anterior também é lido, porque
    edital publicado em dezembro tem inscrição em janeiro.
    """
    hoje_ = hoje_ or date.today()
    anos = [hoje_.year]
    if hoje_.month <= 3:
        anos.append(hoje_.year - 1)
    return [f"{base.rstrip('/')}/editais-{ano}" for ano in anos]


def _conteudo(sopa):
    """A seção de conteúdo, com recuos progressivos caso o tema mude."""
    for seletor in [
        {"name": "section", "class_": "h-entry__e-content"},
        {"name": "section", "class_": "e-content"},
        {"name": "article", "id": "main"},
        {"name": "article"},
    ]:
        achado = sopa.find(**seletor)
        if achado:
            return achado
    return sopa


def _rotulo(elemento) -> str:
    return re.sub(r"\s+", " ", elemento.get_text(" ", strip=True)).strip()


def coletar(fonte: dict) -> list[Edital]:
    base = fonte.get("base_url") or "https://secti.ma.gov.br/programas-ou-campanhas"
    encontrados: list[Edital] = []
    vistos: set[str] = set()

    for indice, url in enumerate(urls_do_ano(base)):
        sopa = buscar(url)
        if sopa is None:
            if indice == 0:
                raise FonteIndisponivel(url)
            continue        # ano anterior indisponível não é motivo de alarme

        secao = _conteudo(sopa)
        titulo_atual = ""
        grupos: list[dict] = []

        # Percorre em ordem de documento: texto vira título do grupo,
        # links de PDF entram no grupo corrente.
        for elemento in secao.find_all(
                ["p", "h2", "h3", "h4", "h5", "strong", "li", "a"]):

            if elemento.name == "a":
                continue        # tratados dentro do <li>

            if elemento.name == "li":
                link = elemento.find("a", href=True)
                if not link or ".pdf" not in link["href"].lower():
                    continue
                documento = {
                    "rotulo": _rotulo(link),
                    "url": normalizar_url(urljoin(url, link["href"])),
                }
                if not grupos or grupos[-1]["titulo"] != titulo_atual:
                    grupos.append({"titulo": titulo_atual, "documentos": []})
                grupos[-1]["documentos"].append(documento)
                continue

            texto = _rotulo(elemento)
            if texto and len(texto) < 300 and not elemento.find("a", href=True):
                titulo_atual = texto

        for grupo in grupos:
            edital = _montar(grupo, fonte, url)
            if edital and edital.url not in vistos:
                vistos.add(edital.url)
                encontrados.append(edital)

        time.sleep(1)

    return encontrados


def _montar(grupo: dict, fonte: dict, origem: str) -> Edital | None:
    documentos = grupo["documentos"]
    if not documentos:
        return None

    # O documento principal é o primeiro que parece edital; se nenhum
    # parecer, usa o primeiro da lista.
    principal = next(
        (d for d in documentos
         if PADRAO_EDITAL.match(d["rotulo"]) and not PADRAO_ANEXO.search(d["rotulo"])),
        documentos[0],
    )

    titulo = grupo["titulo"] or principal["rotulo"]
    # Remove a numeração da lista: "3 - SELEÇÃO DE BOLSISTAS" -> "SELEÇÃO…"
    titulo = re.sub(r"^\s*\d+\s*[-–—]\s*", "", titulo)
    if principal["rotulo"] and principal["rotulo"].lower() not in titulo.lower():
        titulo = f"{principal['rotulo']} — {titulo}"

    # Os rótulos dos anexos entram na descrição: é assim que uma errata ou
    # uma lista de aprovados nova é detectada como alteração do edital.
    anexos = [d["rotulo"] for d in documentos if d["url"] != principal["url"]]

    return Edital(
        id=id_de(principal["url"]),
        url=principal["url"],
        titulo=titulo[:400],
        fonte=fonte["id"],
        fonte_nome=fonte["nome"],
        descricao=" | ".join(anexos)[:600],
    )


def enriquecer(edital: Edital) -> None:
    """Abre o PDF do edital para achar a data de encerramento das inscrições."""
    texto = baixar_pdf(edital.url)
    if not texto.strip():
        edital.prazo_confianca = "ausente"
        return
    prazo = extrair_prazo(texto)
    if prazo:
        edital.prazo = prazo.isoformat()
        edital.prazo_confianca = "extraido"
    else:
        edital.prazo_confianca = "ausente"
    time.sleep(1)
