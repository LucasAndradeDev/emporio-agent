"""Ferramentas expostas ao LLM.

A docstring de cada ferramenta é o que o modelo lê para decidir quando usá-la,
então ela descreve o "quando" (não só o "o quê"). As ferramentas devolvem JSON
para o modelo ler os campos sem ambiguidade.
"""

from __future__ import annotations

import json
from typing import Literal

from langchain.tools import tool

import data
import policies


def _json(valor) -> str:
    return json.dumps(valor, ensure_ascii=False, default=str)


@tool
def buscar_produtos(
    termo: str | None = None,
    categoria: str | None = None,
    preco_max: float | None = None,
    preco_min: float | None = None,
    incluir_indisponiveis: bool = False,
) -> str:
    """Busca instrumentos no catálogo da loja.

    Use quando o cliente quer opções ou recomendações: "violões até R$ 1000",
    "tem guitarra Fender?", "ukulele para iniciante". Os resultados vêm do mais
    barato para o mais caro, já com preço de tabela, preço no PIX ou promoção ativa.

    Args:
        termo: palavras do nome ou da descrição (marca, modelo, característica). Ex.: "fender", "7 cordas", "nylon".
        categoria: Guitarras, Baixos, Baterias e Percussão, Teclados e Pianos, Violões,
            Instrumentos de Sopro (Madeiras), Instrumentos de Sopro (Metais), Cordas Orquestrais, Ukuleles.
        preco_max: preço máximo em reais (considera o preço promocional, se houver).
        preco_min: preço mínimo em reais.
        incluir_indisponiveis: True para listar também itens sem estoque, descontinuados ou em breve.
    """
    resultado = data.buscar_produtos(
        termo=termo,
        categoria=categoria,
        preco_max=preco_max,
        preco_min=preco_min,
        apenas_disponiveis=not incluir_indisponiveis,
    )
    if not resultado:
        return _json({"resultado": [], "mensagem": "Nenhum produto encontrado com esses filtros."})
    return _json({"resultado": resultado})


@tool
def detalhes_produto(nome_ou_id: str) -> str:
    """Retorna preço, disponibilidade, promoção ativa e especificações de UM produto.

    Use sempre que o cliente perguntar preço, estoque ou detalhes de um modelo
    específico ("quanto custa o Takamine GD20?", "o Yamaha C40 tem em estoque?").
    Se o produto estiver indisponível, a resposta já traz alternativas parecidas.
    Se vier "ambiguo": true, pergunte ao cliente qual das opções ele quer.

    Args:
        nome_ou_id: nome (ou parte do nome) do produto, ou o ID numérico.
    """
    resultado = data.detalhes_produto(nome_ou_id)
    if resultado is None:
        return _json({"erro": "Produto não encontrado no catálogo."})
    return _json(resultado)


@tool
def status_pedido(numero_pedido: str, email_ou_telefone: str) -> str:
    """Consulta status, itens, rastreio e previsão de entrega de um pedido.

    Só chame depois de ter OS DOIS dados do cliente: o número do pedido e o
    e-mail ou telefone cadastrado. Se faltar algum, peça ao cliente antes.
    A ferramenta confere a identidade (LGPD) e só devolve o pedido se o contato bater.

    Args:
        numero_pedido: número do pedido informado pelo cliente.
        email_ou_telefone: e-mail ou telefone cadastrado na compra.
    """
    return _json(data.status_pedido(numero_pedido, email_ou_telefone))


@tool
def consultar_politica(
    secao: Literal[
        "sobre_a_loja",
        "horario",
        "pagamento",
        "trocas_e_devolucoes",
        "frete_e_entrega",
        "promocoes",
        "atendimento",
        "garantia",
        "privacidade",
    ],
) -> str:
    """Consulta o manual oficial de políticas da loja.

    Use para qualquer regra ou informação institucional, em vez de responder de memória:
    - sobre_a_loja: endereço, telefone, e-mail, o que a loja vende (e o que NÃO vende)
    - horario: horário de funcionamento
    - pagamento: formas de pagamento, desconto no PIX, parcelamento
    - trocas_e_devolucoes: arrependimento, defeito, troca por preferência, itens não elegíveis
    - frete_e_entrega: valores e prazos de frete, transportadoras, rastreamento
    - promocoes: calendário de campanhas e regras (cumulatividade, estoque)
    - atendimento: como agir com produto esgotado, descontinuado, promoção expirada, reclamação
    - garantia: garantia legal e do fabricante, o que não cobre
    - privacidade: uso de dados pessoais (LGPD)
    """
    return policies.consultar_politica(secao)


TOOLS = [buscar_produtos, detalhes_produto, status_pedido, consultar_politica]


if __name__ == "__main__":
    print(buscar_produtos.invoke({"categoria": "ukulele", "preco_max": 300}))
    print()
    print(detalhes_produto.invoke({"nome_ou_id": "takamine gd20"}))
    print()
    print(status_pedido.invoke({"numero_pedido": "17", "email_ou_telefone": "(67) 99999-0000"}))
    print()
    print(consultar_politica.invoke({"secao": "trocas_e_devolucoes"})[:400])
    print()
    for t in TOOLS:
        print(t.name, "->", list(t.args))
