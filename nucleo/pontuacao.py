"""Pontuação de relevância.

Regra de ouro: a pontuação ordena, nunca descarta. Todo edital coletado
aparece no portal. O que a pontuação decide é a ordem da lista e o que
merece interromper o seu dia via Telegram.
"""

from __future__ import annotations

import unicodedata

from nucleo.modelo import Edital


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def pontuar(edital: Edital, perfil: dict) -> None:
    alvo = normalizar(f"{edital.titulo} {edital.descricao}")
    total = 0
    motivos: list[str] = []

    for regra in perfil.get("termos", []):
        if normalizar(regra["termo"]) in alvo:
            total += regra["peso"]
            motivos.append(regra["termo"])

    for regra in perfil.get("rebaixar", []):
        if normalizar(regra["termo"]) in alvo:
            total += regra["peso"]
            motivos.append(f"−{regra['termo']}")

    urgencia = perfil.get("urgencia", {})
    dias = edital.dias_restantes()
    if dias is not None and dias >= 0:
        if dias <= urgencia.get("dias_criticos", 5):
            total += urgencia.get("bonus_critico", 10)
            motivos.append(f"fecha em {dias} dia(s)")
        elif dias <= urgencia.get("dias_proximos", 15):
            total += urgencia.get("bonus_proximo", 4)

    edital.pontuacao = total
    edital.motivos = motivos


def ordenar(editais: list[Edital]) -> list[Edital]:
    """Encerrados vão para o fim. Entre os abertos, prazo mais curto e
    pontuação mais alta vêm primeiro."""

    def chave(e: Edital):
        dias = e.dias_restantes()
        sem_prazo = dias is None
        return (
            e.encerrado(),
            -e.pontuacao,
            sem_prazo,
            dias if dias is not None else 9999,
        )

    return sorted(editais, key=chave)
