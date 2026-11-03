"""Extração e indexação do manual de políticas da loja.

O manual tem 8 páginas (~11 mil caracteres). Em vez de embeddings e banco vetorial,
ele é dividido pelas seções numeradas do próprio documento, e o agente consulta a
seção pelo tema. Para um documento deste tamanho e com estrutura clara, a busca por
seção é exata, barata e fácil de auditar.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from pypdf import PdfReader

PDF_PATH = Path(__file__).parent / "data" / "políticas_da_loja.pdf"

# Chave usada pelo agente -> número da seção no manual.
SECOES = {
    "sobre_a_loja": 1,  # quem somos, endereço, telefone, o que a loja (não) vende
    "horario": 2,
    "pagamento": 3,  # formas de pagamento, desconto PIX, parcelamento
    "trocas_e_devolucoes": 4,
    "frete_e_entrega": 5,  # frete, prazos, rastreamento
    "promocoes": 6,  # calendário e regras de promoções
    "atendimento": 7,  # diretrizes de atendimento e situações especiais
    "garantia": 8,
    "privacidade": 9,  # LGPD
}

_RUIDO = re.compile(r"^\s*(Página \d+|Empório da Música Manual de Políticas e Procedimentos)\s*$")
_TITULO = re.compile(r"^(\d{1,2})\. (.+)$")


@lru_cache(maxsize=1)
def texto_manual() -> str:
    paginas = PdfReader(PDF_PATH).pages[1:]  # a página 1 é só a capa
    linhas = []
    for pagina in paginas:
        for linha in pagina.extract_text(extraction_mode="layout").splitlines():
            linha = re.sub(r"[ \t]+", " ", linha).strip()
            if linha and not _RUIDO.match(linha):
                linhas.append(linha)
    return "\n".join(linhas)


@lru_cache(maxsize=1)
def secoes_manual() -> dict[int, str]:
    """Divide o manual nas seções de primeiro nível (1. ..., 2. ..., ...)."""
    secoes: dict[int, list[str]] = {}
    atual = 0
    for linha in texto_manual().splitlines():
        titulo = _TITULO.match(linha)
        # Só conta como título o número da próxima seção; isso evita confundir
        # listas numeradas internas (ex.: "2. Entendimento" no fluxo da seção 7.2).
        if titulo and int(titulo.group(1)) == atual + 1:
            atual += 1
        if atual:
            secoes.setdefault(atual, []).append(linha)
    return {numero: "\n".join(linhas) for numero, linhas in secoes.items()}


def consultar_politica(secao: str) -> str:
    numero = SECOES.get(secao)
    if numero is None:
        return f"Seção desconhecida. Opções: {', '.join(SECOES)}."
    return secoes_manual().get(numero, "Seção não encontrada no manual.")


if __name__ == "__main__":
    for chave, numero in SECOES.items():
        texto = consultar_politica(chave)
        print(f"== {chave} (seção {numero}, {len(texto)} caracteres) ==")
        print(texto.splitlines()[0])
    print()
    print(consultar_politica("horario"))
