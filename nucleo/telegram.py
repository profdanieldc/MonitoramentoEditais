"""Alerta pelo Telegram.

O portal é para consulta; o alerta é o produto. Editais como os da SECTI
abrem e fecham em três dias — se você depender de lembrar de abrir o site,
perde.
"""

from __future__ import annotations

import html
import os

import requests

from nucleo.modelo import Edital

LIMITE_MENSAGEM = 4000  # o Telegram corta em 4096


def _escapar(texto: str) -> str:
    return html.escape(texto, quote=False)


def _linha(edital: Edital) -> str:
    dias = edital.dias_restantes()
    if dias is None:
        prazo = "prazo não identificado"
    elif dias < 0:
        prazo = "encerrado"
    elif dias == 0:
        prazo = "<b>fecha hoje</b>"
    else:
        prazo = f"<b>{dias} dia(s)</b> para o fim"
    return (
        f'• <a href="{_escapar(edital.url)}">{_escapar(edital.titulo[:160])}</a>\n'
        f"  {_escapar(edital.fonte_nome)} · {prazo}"
    )


def montar_mensagem(novos: list[Edital], alterados: list[Edital],
                    silenciosas: list[str]) -> str | None:
    blocos: list[str] = []

    if novos:
        blocos.append("<b>Editais novos</b>\n" + "\n".join(_linha(e) for e in novos))
    if alterados:
        blocos.append(
            "<b>Retificados ou atualizados</b>\n"
            + "\n".join(_linha(e) for e in alterados)
        )
    if silenciosas:
        blocos.append(
            "<b>Atenção</b>\n"
            + "\n".join(f"• {_escapar(f)} sem resultados há dias — pode ter quebrado"
                        for f in silenciosas)
        )

    if not blocos:
        return None
    return "\n\n".join(blocos)[:LIMITE_MENSAGEM]


def enviar(mensagem: str) -> bool:
    token = os.environ.get("TELEGRAM_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[telegram] TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID ausentes; não enviei.")
        return False

    resposta = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat,
            "text": mensagem,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    if resposta.status_code != 200:
        print(f"[telegram] falhou ({resposta.status_code}): {resposta.text[:300]}")
        return False
    return True
