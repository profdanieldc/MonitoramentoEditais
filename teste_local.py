#!/usr/bin/env python3
"""Teste sem rede.

Reproduz a estrutura da tabela do Plone com itens reais da STED e roda o
pipeline duas vezes: a segunda com um edital alterado e um inédito, para
conferir que retificação e novidade são distinguidas corretamente.

Rode com:  python teste_local.py
"""

from __future__ import annotations

import json
from pathlib import Path

from bs4 import BeautifulSoup

from coletores import base, plone
from nucleo.modelo import ARQUIVO_DADOS, carregar, editais_de, salvar
from nucleo.pontuacao import ordenar, pontuar

BASE = "https://portalpadrao.ufma.br/dted/editais/"


def montar_html(linhas: list[tuple[str, str, str, str]]) -> str:
    corpo = "\n".join(
        f'<tr><td><a href="{BASE}{slug}?_authenticator=abc123">{titulo}</a></td>'
        f"<td>{descricao}</td><td>{data}</td></tr>"
        for slug, titulo, descricao, data in linhas
    )
    return f"""<html><body><table class="listing"><thead><tr>
    <th>Título</th><th>Descrição</th><th>ModificationDate</th></tr></thead>
    <tbody>{corpo}</tbody></table></body></html>"""


RODADA_1 = [
    ("edital-17-2026", "Edital Nº17/2026 | Prorrogação da validade do resultado "
     "do processo seletivo regido pelo Edital nº 36/2023", "", "28/08/2026 17h31"),
    ("edital-10-2026", "Edital Nº10/2026 | Processo Seletivo para Mediador "
     "Pedagógico Residente dos cursos de Graduação EaD",
     "EDITAL Nº10/2026 - STED", "31/07/2026 12h10"),
    ("edital-04-2025", "Edital N°04/2025 | Processo Seletivo para formação de "
     "cadastro de reserva de Professor Formador interno e externo",
     "EDITAL N°04/2025 - STED", "10/08/2026 17h24"),
]

RODADA_2 = [
    # inédito, com termos de alto peso
    ("edital-18-2026", "Edital Nº18/2026 | Seleção de bolsista para projeto de "
     "inteligência artificial aplicada à análise de dados",
     "EDITAL Nº18/2026 - STED", "06/09/2026 09h00"),
    # mesmo edital da rodada 1, agora retificado (data mudou)
    ("edital-10-2026", "Edital Nº10/2026 | Processo Seletivo para Mediador "
     "Pedagógico Residente dos cursos de Graduação EaD — retificado",
     "EDITAL Nº10/2026 - STED", "05/09/2026 14h22"),
    # inalterado
    ("edital-17-2026", "Edital Nº17/2026 | Prorrogação da validade do resultado "
     "do processo seletivo regido pelo Edital nº 36/2023", "", "28/08/2026 17h31"),
]


def rodada(linhas, perfil) -> tuple[int, int]:
    html = montar_html(linhas)
    base.buscar = lambda url, **kw: BeautifulSoup(html, "html.parser")
    plone.buscar = base.buscar

    fonte = {"id": "sted-ufma", "nome": "STED/UFMA", "tipo": "plone",
             "url": "https://exemplo/coleção", "paginas": 1, "abrir_itens": False}

    dados = carregar()
    conhecidos = editais_de(dados)
    novos = alterados = 0

    for achado in plone.coletar(fonte):
        anterior = conhecidos.get(achado.id)
        if anterior is None:
            achado.visto_em = achado.atualizado_em = "2026-09-07T00:00:00+00:00"
            pontuar(achado, perfil)
            conhecidos[achado.id] = achado
            novos += 1
        elif anterior.assinatura() != achado.assinatura():
            anterior.titulo = achado.titulo
            anterior.modificado_em = achado.modificado_em
            anterior.revisao += 1
            pontuar(anterior, perfil)
            alterados += 1

    salvar(ordenar(list(conhecidos.values())), {})
    return novos, alterados


def main() -> None:
    import yaml
    cfg = yaml.safe_load(Path("config/perfis.yaml").read_text(encoding="utf-8"))
    perfil = cfg["perfis"]["daniel"]

    if ARQUIVO_DADOS.exists():
        ARQUIVO_DADOS.unlink()

    n1, a1 = rodada(RODADA_1, perfil)
    print(f"rodada 1 → {n1} novo(s), {a1} atualizado(s)")

    n2, a2 = rodada(RODADA_2, perfil)
    print(f"rodada 2 → {n2} novo(s), {a2} atualizado(s)")

    dados = json.loads(ARQUIVO_DADOS.read_text(encoding="utf-8"))
    print(f"\nacervo: {len(dados['editais'])} edital(is), em ordem de relevância\n")
    for e in dados["editais"]:
        marca = f"rev{e['revisao']}" if e["revisao"] > 1 else "    "
        print(f"  {e['pontuacao']:>4}  {marca}  {e['titulo'][:66]}")
        if e["motivos"]:
            print(f"        {', '.join(e['motivos'])}")

    assert "_authenticator" not in json.dumps(dados), "token vazou para o JSON"
    print("\nURLs gravadas sem o token do Plone.")


if __name__ == "__main__":
    main()
