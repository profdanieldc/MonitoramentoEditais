"""Utilidades compartilhadas pelos coletores."""

from __future__ import annotations

import re
import time
from datetime import date

import requests
from bs4 import BeautifulSoup

CABECALHO = {
    "User-Agent": (
        "monitor-editais/0.1 (projeto pessoal de acompanhamento de editais; "
        "contato via GitHub)"
    )
}

MESES = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
    "outubro": 10, "novembro": 11, "dezembro": 12,
}


def buscar(url: str, tentativas: int = 3, espera: float = 3.0) -> BeautifulSoup | None:
    """Baixa uma página e devolve a árvore HTML. None se falhar."""
    for tentativa in range(tentativas):
        try:
            resposta = requests.get(url, headers=CABECALHO, timeout=30)
            resposta.raise_for_status()
            resposta.encoding = resposta.apparent_encoding or "utf-8"
            return BeautifulSoup(resposta.text, "html.parser")
        except requests.RequestException as erro:
            if tentativa == tentativas - 1:
                print(f"  [erro] {url}: {erro}")
                return None
            time.sleep(espera * (tentativa + 1))
    return None


def data_numerica(texto: str) -> date | None:
    """Converte '28/08/2026' (ou 28/08/26) em date."""
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", texto)
    if not m:
        return None
    dia, mes, ano = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if ano < 100:
        ano += 2000
    try:
        return date(ano, mes, dia)
    except ValueError:
        return None


def data_por_extenso(texto: str) -> date | None:
    """Converte '23 de março de 2026' em date."""
    padrao = r"\b(\d{1,2})\s+de\s+([a-zç]+)\s+de\s+(\d{4})\b"
    m = re.search(padrao, texto.lower())
    if not m:
        return None
    mes = MESES.get(m.group(2))
    if not mes:
        return None
    try:
        return date(int(m.group(3)), mes, int(m.group(1)))
    except ValueError:
        return None


# Trechos que costumam anteceder a data de encerramento das inscrições.
PISTAS_PRAZO = [
    r"inscri[çc][õo]es?[^.\n]{0,60}?at[ée]",
    r"data\s+limite\s+para\s+inscri[çc][õo]es",
    r"prazo\s+(?:final\s+)?(?:de|para)\s+(?:inscri[çc][õo]es|submiss[ãa]o)",
    r"per[íi]odo\s+de\s+submiss[ãa]o[^.\n]{0,60}?a\s",
    r"submiss[ãa]o[^.\n]{0,40}?at[ée]",
    r"encerramento\s+das\s+inscri[çc][õo]es",
]


def extrair_prazo(texto: str) -> date | None:
    """Tenta achar a data de encerramento no corpo da página.

    Best-effort de propósito: é melhor devolver None e o portal mostrar
    'prazo não identificado' do que cravar uma data errada e você confiar
    nela. Quando devolve None, o link para o edital continua lá.
    """
    limpo = re.sub(r"\s+", " ", texto)
    for pista in PISTAS_PRAZO:
        for m in re.finditer(pista, limpo, flags=re.IGNORECASE):
            trecho = limpo[m.end(): m.end() + 120]
            achada = data_numerica(trecho) or data_por_extenso(trecho)
            if achada:
                return achada
    return None


def texto_da_pagina(sopa: BeautifulSoup) -> str:
    for tag in sopa(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    return sopa.get_text(" ", strip=True)
