"""Modelo de dados e persistência.

O "banco de dados" é um único arquivo JSON versionado no próprio
repositório. Isso dá histórico de graça: cada rodada vira um commit, e
o git guarda o que mudou.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from pathlib import Path

# O acervo mora dentro de docs/ para que o GitHub Pages consiga servi-lo
# direto ao portal, sem precisar copiar arquivo entre pastas.
ARQUIVO_DADOS = Path(__file__).resolve().parent.parent / "docs" / "editais.json"


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hoje() -> date:
    return datetime.now(timezone.utc).date()


def id_de(url: str) -> str:
    """A URL é a chave natural do edital.

    Nunca use a data de modificação como chave: na STED, um edital antigo
    que sofre qualquer alteração salta para o topo da listagem, e daria
    a falsa impressão de ser novidade.
    """
    return hashlib.sha1(url.strip().encode("utf-8")).hexdigest()[:16]


@dataclass
class Edital:
    id: str
    url: str
    titulo: str
    fonte: str
    fonte_nome: str
    descricao: str = ""
    publicado_em: str | None = None      # ISO date, quando conhecido
    modificado_em: str | None = None     # ISO datetime informado pela fonte
    prazo: str | None = None             # ISO date de encerramento
    prazo_confianca: str = "ausente"     # extraido | ausente
    pontuacao: int = 0
    motivos: list[str] = field(default_factory=list)

    # Controle interno
    visto_em: str = ""        # primeira vez que o coletor encontrou
    atualizado_em: str = ""   # última vez que algo mudou
    revisao: int = 1          # incrementa a cada mudança detectada

    def assinatura(self) -> str:
        """O que define 'mudou'. Se qualquer um destes campos difere,
        houve retificação e o edital volta a aparecer, mesmo arquivado."""
        base = f"{self.titulo}|{self.descricao}|{self.modificado_em}|{self.prazo}"
        return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]

    def dias_restantes(self) -> int | None:
        if not self.prazo:
            return None
        try:
            return (date.fromisoformat(self.prazo) - hoje()).days
        except ValueError:
            return None

    def encerrado(self) -> bool:
        d = self.dias_restantes()
        return d is not None and d < 0


VAZIO = {"gerado_em": None, "fontes": {}, "editais": []}


def carregar() -> dict:
    """Lê o acervo. Arquivo ausente, vazio ou corrompido devolve acervo
    vazio em vez de derrubar a rodada: recomeçar do zero é recuperável,
    perder a coleta do dia não é."""
    if not ARQUIVO_DADOS.exists():
        return dict(VAZIO)
    try:
        conteudo = ARQUIVO_DADOS.read_text(encoding="utf-8").strip()
    except OSError as erro:
        print(f"[aviso] não consegui ler o acervo ({erro}); recomeçando vazio")
        return dict(VAZIO)
    if not conteudo:
        print("[aviso] acervo vazio; recomeçando do zero")
        return dict(VAZIO)
    try:
        dados = json.loads(conteudo)
    except json.JSONDecodeError as erro:
        print(f"[aviso] acervo ilegível (linha {erro.lineno}); recomeçando do zero")
        return dict(VAZIO)
    if not isinstance(dados, dict):
        print("[aviso] acervo em formato inesperado; recomeçando do zero")
        return dict(VAZIO)
    return dados


def salvar(editais: list[Edital], estado_fontes: dict) -> bool:
    """Grava o acervo. Devolve True se o arquivo mudou de verdade.

    Carimbos de data mudam a cada rodada e, sozinhos, gerariam um commit
    a cada 12 horas para sempre. Só vale gravar quando o conteúdo mudou.
    """
    ARQUIVO_DADOS.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "gerado_em": agora_iso(),
        "fontes": estado_fontes,
        "editais": [asdict(e) for e in editais],
    }

    def sem_carimbos(d: dict) -> str:
        copia = {
            "editais": d.get("editais", []),
            "fontes": {
                id_fonte: {k: v for k, v in estado.items()
                           if k not in ("ultima_rodada", "ultimo_resultado")}
                for id_fonte, estado in d.get("fontes", {}).items()
            },
        }
        return json.dumps(copia, ensure_ascii=False, sort_keys=True)

    if ARQUIVO_DADOS.exists():
        try:
            with ARQUIVO_DADOS.open(encoding="utf-8") as f:
                if sem_carimbos(json.load(f)) == sem_carimbos(payload):
                    return False
        except (json.JSONDecodeError, OSError):
            pass

    with ARQUIVO_DADOS.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return True


def editais_de(dados: dict) -> dict[str, Edital]:
    saida = {}
    for bruto in dados.get("editais", []):
        campos = {k: v for k, v in bruto.items() if k in Edital.__dataclass_fields__}
        edital = Edital(**campos)
        saida[edital.id] = edital
    return saida
