#!/usr/bin/env python3
"""Rodada de coleta.

Uso:
    python executar.py              # coleta, grava e avisa no Telegram
    python executar.py --sem-alerta # coleta e grava, sem mandar mensagem
    python executar.py --fonte sted-ufma
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from coletores import plone, secti  # noqa: E402
from coletores.base import FonteIndisponivel  # noqa: E402
from nucleo import telegram  # noqa: E402
from nucleo.modelo import (  # noqa: E402
    Edital, agora_iso, carregar, editais_de, hoje, salvar,
)
from nucleo.pontuacao import ordenar, pontuar  # noqa: E402

RAIZ = Path(__file__).resolve().parent
COLETORES = {"plone": plone, "secti": secti}


def ler_config(nome: str) -> dict:
    with (RAIZ / "config" / nome).open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sem-alerta", action="store_true")
    parser.add_argument("--fonte", help="roda só a fonte com este id")
    parser.add_argument("--perfil", default="daniel")
    args = parser.parse_args()

    cfg_fontes = ler_config("fontes.yaml")
    cfg_perfis = ler_config("perfis.yaml")
    perfil = cfg_perfis["perfis"][args.perfil]

    dados = carregar()
    conhecidos = editais_de(dados)
    estado_fontes = dict(dados.get("fontes", {}))

    novos: list[Edital] = []
    alterados: list[Edital] = []
    falhas: list[tuple[str, int]] = []

    for fonte in cfg_fontes["fontes"]:
        if not fonte.get("ativa"):
            continue
        if args.fonte and fonte["id"] != args.fonte:
            continue

        modulo = COLETORES.get(fonte["tipo"])
        if modulo is None:
            print(f"[{fonte['id']}] tipo de coletor desconhecido: {fonte['tipo']}")
            continue

        estado = estado_fontes.setdefault(fonte["id"], {})
        estado["nome"] = fonte["nome"]
        estado["sigla"] = fonte.get("sigla", fonte["nome"][:5])
        estado["cor"] = fonte.get("cor", "#5E6B63")
        estado["logo"] = fonte.get("logo")
        estado["ultima_rodada"] = agora_iso()

        print(f"[{fonte['id']}] coletando…")
        try:
            encontrados = modulo.coletar(fonte)
        except FonteIndisponivel:
            estado["falhas_seguidas"] = estado.get("falhas_seguidas", 0) + 1
            falhas.append((fonte["nome"], estado["falhas_seguidas"]))
            print(f"[{fonte['id']}] indisponível "
                  f"({estado['falhas_seguidas']} rodada(s) seguida(s))")
            continue
        except Exception as erro:  # um coletor quebrado não derruba os outros
            estado["falhas_seguidas"] = estado.get("falhas_seguidas", 0) + 1
            falhas.append((fonte["nome"], estado["falhas_seguidas"]))
            print(f"[{fonte['id']}] falhou: {type(erro).__name__}: {erro}")
            continue

        estado["falhas_seguidas"] = 0
        estado["itens_ultima_rodada"] = len(encontrados)
        if encontrados:
            estado["ultimo_resultado"] = hoje().isoformat()
        print(f"[{fonte['id']}] {len(encontrados)} item(ns) na listagem")

        for achado in encontrados:
            anterior = conhecidos.get(achado.id)

            if anterior is None:
                achado.visto_em = agora_iso()
                achado.atualizado_em = achado.visto_em
                achado.revisao = 1
                if fonte.get("abrir_itens") and hasattr(modulo, "enriquecer"):
                    modulo.enriquecer(achado)
                pontuar(achado, perfil)
                conhecidos[achado.id] = achado
                novos.append(achado)
                continue

            # Já conhecido: mudou alguma coisa?
            if anterior.assinatura() != achado.assinatura():
                anterior.titulo = achado.titulo
                anterior.descricao = achado.descricao
                anterior.modificado_em = achado.modificado_em
                anterior.atualizado_em = agora_iso()
                anterior.revisao += 1
                if fonte.get("abrir_itens") and hasattr(modulo, "enriquecer"):
                    modulo.enriquecer(anterior)
                pontuar(anterior, perfil)
                alterados.append(anterior)
            else:
                # Repontua mesmo sem mudança: o bônus de urgência varia
                # com o passar dos dias.
                pontuar(anterior, perfil)

    # Fontes em silêncio prolongado provavelmente quebraram.
    limite = int(cfg_fontes.get("alerta_silencio_dias", 7))
    silenciosas: list[str] = []
    for id_fonte, estado in estado_fontes.items():
        ultimo = estado.get("ultimo_resultado")
        if not ultimo:
            continue
        if date.fromisoformat(ultimo) < hoje() - timedelta(days=limite):
            silenciosas.append(estado.get("nome", id_fonte))

    lista = ordenar(list(conhecidos.values()))
    mudou = salvar(lista, estado_fontes)
    print(f"\n{len(novos)} novo(s), {len(alterados)} atualizado(s), "
          f"{len(lista)} no acervo"
          + ("" if mudou else " — nada mudou, arquivo não reescrito"))

    limiar = perfil.get("limiar_alerta", 0)
    alerta_novos = [e for e in novos if e.pontuacao >= limiar and not e.encerrado()]
    alerta_alterados = [e for e in alterados
                        if e.pontuacao >= limiar and not e.encerrado()]

    if args.sem_alerta:
        print("(--sem-alerta: mensagem não enviada)")
        return 0

    mensagem = telegram.montar_mensagem(
        alerta_novos, alerta_alterados, silenciosas, falhas)
    if mensagem is None:
        print("Nada acima do limiar hoje; nenhuma mensagem enviada.")
        return 0

    telegram.enviar(mensagem)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
