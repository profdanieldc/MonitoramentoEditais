"""Coletor de coleções Plone (portalpadrao.ufma.br).

A coleção devolve uma tabela com título, descrição e data de modificação,
ordenada da mais recente para a mais antiga. Como o que é novo está sempre
no topo, a primeira página basta para o monitoramento diário.

O mesmo coletor serve para qualquer setor da UFMA hospedado no mesmo Plone:
é só apontar outra URL em config/fontes.yaml.
"""

from __future__ import annotations

import time
from urllib.parse import urljoin, urlparse, urlunparse

from coletores.base import (
    FonteIndisponivel, buscar, data_numerica, extrair_prazo, texto_da_pagina,
)
from nucleo.modelo import Edital, id_de


def limpar_url(url: str) -> str:
    """Remove parâmetros de consulta.

    O Plone anexa um token anti-CSRF (`_authenticator`) aos links, inclusive
    para visitantes anônimos. Ele muda a cada visita e o coletor não precisa
    dele — mas, se ficasse na URL, cada rodada acharia que o edital é novo.
    """
    partes = urlparse(url)
    return urlunparse((partes.scheme, partes.netloc, partes.path, "", "", ""))


def _linhas_da_tabela(sopa):
    tabela = sopa.find("table")
    if not tabela:
        return []
    corpo = tabela.find("tbody") or tabela
    return corpo.find_all("tr")


def coletar(fonte: dict) -> list[Edital]:
    base_url = fonte["url"]
    encontrados: list[Edital] = []
    vistos: set[str] = set()

    for pagina in range(int(fonte.get("paginas", 1))):
        url = base_url if pagina == 0 else f"{base_url}?b_start:int={pagina * 10}"
        sopa = buscar(url)
        if sopa is None:
            if pagina == 0:
                raise FonteIndisponivel(url)
            break        # páginas seguintes falhando: usa o que já veio

        linhas = _linhas_da_tabela(sopa)
        if not linhas:
            print(f"  [aviso] nenhuma linha encontrada em {url}")
            break

        for linha in linhas:
            celulas = linha.find_all(["td", "th"])
            if not celulas:
                continue
            link = celulas[0].find("a", href=True)
            if not link:
                continue

            url_item = limpar_url(urljoin(url, link["href"]))
            if url_item in vistos:
                continue
            vistos.add(url_item)

            titulo = link.get_text(" ", strip=True)
            descricao = celulas[1].get_text(" ", strip=True) if len(celulas) > 1 else ""
            texto_data = celulas[2].get_text(" ", strip=True) if len(celulas) > 2 else ""
            modificado = data_numerica(texto_data)

            encontrados.append(
                Edital(
                    id=id_de(url_item),
                    url=url_item,
                    titulo=titulo,
                    fonte=fonte["id"],
                    fonte_nome=fonte["nome"],
                    descricao=descricao,
                    modificado_em=modificado.isoformat() if modificado else None,
                )
            )

        time.sleep(1)  # cortesia com o servidor da UFMA

    return encontrados


def enriquecer(edital: Edital) -> None:
    """Abre a página do edital para tentar achar o prazo de inscrição.

    Só vale a pena chamar para itens novos ou alterados — abrir todos os
    duzentos e tantos itens a cada rodada seria desperdício e má educação
    com o servidor.
    """
    sopa = buscar(edital.url)
    if sopa is None:
        return
    texto = texto_da_pagina(sopa)
    prazo = extrair_prazo(texto)
    if prazo:
        edital.prazo = prazo.isoformat()
        edital.prazo_confianca = "extraido"
    else:
        edital.prazo_confianca = "ausente"
    time.sleep(1)
