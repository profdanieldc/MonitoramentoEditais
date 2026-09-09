"""Utilidades compartilhadas pelos coletores."""

from __future__ import annotations

import io
import re
import time
from datetime import date, datetime
from urllib.parse import unquote, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

CABECALHO = {
    "User-Agent": (
        "monitor-editais/0.1 (projeto pessoal de acompanhamento de editais; "
        "contato via GitHub)"
    )
}

# Poucas tentativas de propósito. Quando a causa é o IP de saída estar
# bloqueado na origem, insistir na mesma máquina não muda nada — o pacote
# vai continuar sendo descartado. Três tentativas cobrem instabilidade real
# do servidor; para o resto, quem resolve é o job de repetição no workflow,
# que sorteia um runner novo e portanto um IP novo.
TENTATIVAS = 3
ESPERAS = [15, 45]            # segundos entre uma tentativa e a seguinte

class FonteIndisponivel(Exception):
    """A fonte não respondeu. Diferente de 'a fonte respondeu e não havia
    nada novo' — que é resultado normal e não deve gerar alerta."""


MESES = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
    "outubro": 10, "novembro": 11, "dezembro": 12,
}


def buscar(url: str, tentativas: int = TENTATIVAS) -> BeautifulSoup | None:
    """Baixa uma página e devolve a árvore HTML. None se falhar em todas.

    Cada tentativa é registrada com horário e duração. Quando algo falhar
    de novo, o log mostra o padrão — se todas as tentativas estouraram no
    mesmo segundo ou se o servidor voltou no meio — em vez de uma única
    mensagem sem contexto.
    """
    ultimo_erro = None

    for numero in range(1, tentativas + 1):
        marca = datetime.now().strftime("%H:%M:%S")
        inicio = time.monotonic()
        try:
            resposta = requests.get(
                url, headers=CABECALHO, timeout=(15, 45)
            )
            resposta.raise_for_status()
            resposta.encoding = resposta.apparent_encoding or "utf-8"
            if numero > 1:
                print(f"    tentativa {numero} às {marca}: ok em "
                      f"{time.monotonic() - inicio:.1f}s")
            return BeautifulSoup(resposta.text, "html.parser")
        except requests.RequestException as erro:
            ultimo_erro = erro
            duracao = time.monotonic() - inicio
            print(f"    tentativa {numero} às {marca}: "
                  f"{type(erro).__name__} após {duracao:.1f}s")
            if numero < tentativas:
                pausa = ESPERAS[min(numero - 1, len(ESPERAS) - 1)]
                print(f"    aguardando {pausa}s")
                time.sleep(pausa)

    print(f"  [erro] {url} não respondeu em {tentativas} tentativas: "
          f"{type(ultimo_erro).__name__}")
    return None


def normalizar_url(url: str) -> str:
    """Deixa a URL em forma canônica para servir de chave.

    O site da SECTI mistura `secti.ma.gov.br` com `www.secti.ma.gov.br` e
    ora codifica acentos (`N%C2%BA`), ora não. Sem normalizar, o mesmo
    edital vira dois registros e é anunciado como novo toda rodada.
    """
    partes = urlparse(url.strip())
    host = partes.netloc.lower().removeprefix("www.")
    caminho = unquote(partes.path)
    return urlunparse((partes.scheme or "https", host, caminho, "", "", ""))


def baixar_pdf(url: str, paginas: int = 6, tentativas: int = 3) -> str:
    """Baixa um PDF e devolve o texto das primeiras páginas.

    Só as primeiras, porque o cronograma de inscrição fica sempre no começo
    e editais têm dezenas de páginas de anexos. Devolve string vazia se o
    arquivo não abrir ou for digitalizado (imagem sem texto).
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        print("    [aviso] pypdf não instalado; prazo não será extraído do PDF")
        return ""

    for numero in range(1, tentativas + 1):
        try:
            resposta = requests.get(url, headers=CABECALHO, timeout=(15, 60))
            resposta.raise_for_status()
            leitor = PdfReader(io.BytesIO(resposta.content))
            trechos = []
            for pagina in leitor.pages[:paginas]:
                try:
                    trechos.append(pagina.extract_text() or "")
                except Exception:
                    continue
            return "\n".join(trechos)
        except requests.RequestException:
            if numero < tentativas:
                time.sleep(10 * numero)
        except Exception as erro:
            print(f"    [aviso] não consegui ler o PDF ({type(erro).__name__})")
            return ""
    return ""


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
    # Cronogramas da SECTI vêm em tabela; ao virar texto, o rótulo fica
    # colado na data. Ex.: "Data limite para inscrições 23 de março de 2026"
    r"data\s+limite\s+(?:para\s+)?(?:as\s+)?inscri[çc][õo]es",
    r"t[ée]rmino\s+das\s+inscri[çc][õo]es",
    r"fim\s+das\s+inscri[çc][õo]es",
    r"prazo\s+de\s+inscri[çc][ãa]o",
    r"per[íi]odo\s+de\s+inscri[çc][õo]es",
    # Último recurso: só a palavra "inscrições". Fica no fim da lista de
    # propósito, para que as pistas específicas sejam tentadas antes.
    # Pega construções soltas como "as inscrições ocorrem no período de
    # 24 de abril a 8 de maio de 2026".
    r"inscri[çc][õo]es",
]

# Intervalo: "13/07/2026 a 13/09/2026" ou "20 de março a 23 de abril de 2026".
# Nesses casos o que interessa é a segunda data, o fechamento.
INTERVALO = re.compile(
    r"(\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}\s+de\s+[a-zç]+(?:\s+de\s+\d{4})?)"
    r"\s*(?:a|at[ée]|à)\s+"
    r"(\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}\s+de\s+[a-zç]+\s+de\s+\d{4})",
    re.IGNORECASE)


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

            # Se o trecho traz um intervalo, o prazo é o fim dele.
            intervalo = INTERVALO.search(trecho)
            if intervalo:
                fim = intervalo.group(2)
                achada = data_numerica(fim) or data_por_extenso(fim)
                if achada:
                    return achada

            achada = data_numerica(trecho) or data_por_extenso(trecho)
            if achada:
                return achada
    return None


def texto_da_pagina(sopa: BeautifulSoup) -> str:
    for tag in sopa(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    return sopa.get_text(" ", strip=True)
