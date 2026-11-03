"""Camada de dados da Empório da Música.

Carrega os CSVs fornecidos pela loja e expõe funções de consulta determinísticas.
O agente nunca calcula preço, desconto ou disponibilidade por conta própria: ele
sempre chama estas funções (regra 7.1 do manual: "nunca fornecer informações sobre
preços, estoque ou prazos sem consultar o sistema").
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
PREFIXO = "desafio_tecnico_ai_eng - "

STATUS_PEDIDO = {
    "pending": "aguardando pagamento",
    "confirmed": "pagamento confirmado, em separação",
    "shipped": "enviado",
    "delivered": "entregue",
    "cancelled": "cancelado",
}

FORMA_PAGAMENTO = {
    "pix": "PIX",
    "debit": "cartão de débito",
    "boleto": "boleto bancário",
}


def normalizar(texto: str) -> str:
    """Minúsculas e sem acentos, para comparar o que o cliente digita com o catálogo."""
    texto = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in texto if not unicodedata.combining(c)).lower().strip()


def apenas_digitos(texto: str) -> str:
    return re.sub(r"\D", "", str(texto))


def _ler(nome: str) -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / f"{PREFIXO}{nome}.csv")


@lru_cache(maxsize=1)
def carregar_dados() -> dict[str, pd.DataFrame]:
    """Lê e trata todas as tabelas uma única vez."""
    categorias = _ler("categories")
    clientes = _ler("customers")
    pedidos = _ler("orders")
    itens = _ler("order_items")
    produtos = _ler("products")
    promocoes = _ler("promotions")

    # Só promoções vigentes entram no preço. Se houver mais de uma ativa para o
    # mesmo produto, vale a de maior desconto (promoções não são cumulativas, 6.2).
    ativas = (
        promocoes[promocoes["is_active"] == 1]
        .sort_values("discount_percent", ascending=False)
        .drop_duplicates("product_id")
        .rename(columns={"description": "promocao", "discount_percent": "desconto_percent"})
        [["product_id", "promocao", "desconto_percent"]]
    )

    produtos = (
        produtos.merge(
            categorias.rename(columns={"name": "categoria"})[["category_id", "categoria"]],
            on="category_id",
            how="left",
        )
        .merge(ativas, on="product_id", how="left")
    )
    produtos["preco_promocional"] = (
        produtos["price_brl"] * (1 - produtos["desconto_percent"] / 100)
    ).round(2)
    produtos["disponivel"] = (produtos["status"] == "active") & (produtos["stock_quantity"] > 0)
    produtos["specs"] = produtos["specs"].apply(_ler_specs)
    produtos["busca_nome"] = produtos["name"].map(normalizar)
    produtos["busca_texto"] = (
        produtos["name"] + " " + produtos["categoria"].fillna("") + " " + produtos["description"].fillna("")
    ).map(normalizar)

    categorias["busca"] = categorias["name"].map(normalizar)
    clientes["telefone_digitos"] = clientes["phone"].map(apenas_digitos)
    clientes["email_norm"] = clientes["email"].map(normalizar)

    return {
        "categorias": categorias,
        "clientes": clientes,
        "pedidos": pedidos,
        "itens": itens,
        "produtos": produtos,
    }


def _ler_specs(valor) -> dict:
    try:
        return json.loads(valor) if isinstance(valor, str) else {}
    except json.JSONDecodeError:
        return {}


def _situacao(linha: pd.Series) -> str:
    if linha["status"] == "discontinued":
        return "descontinuado (não faz mais parte do catálogo)"
    if linha["status"] == "coming_soon":
        return "em breve (ainda não disponível para venda)"
    if linha["stock_quantity"] <= 0:
        return "temporariamente sem estoque"
    return "disponível"


def _produto_para_dict(linha: pd.Series, completo: bool = False) -> dict:
    item = {
        "id": int(linha["product_id"]),
        "nome": linha["name"],
        "categoria": linha["categoria"],
        "preco_tabela": float(linha["price_brl"]),
        "situacao": _situacao(linha),
        "estoque": int(linha["stock_quantity"]),
    }
    if pd.notna(linha["desconto_percent"]):
        item["promocao_ativa"] = {
            "nome": linha["promocao"],
            "desconto_percent": int(linha["desconto_percent"]),
            "preco_promocional": float(linha["preco_promocional"]),
            "observacao": "O desconto de 5% no PIX não se aplica sobre o preço promocional.",
        }
    else:
        item["preco_pix"] = round(float(linha["price_brl"]) * 0.95, 2)
    if completo:
        item["descricao"] = linha["description"]
        item["especificacoes"] = linha["specs"]
    return item


def _resolver_categoria(categoria: str) -> list[int]:
    """Aceita 'violão', 'violoes', 'sopro', etc. e devolve os IDs de categoria."""
    cats = carregar_dados()["categorias"]
    # Compara radicais para tolerar singular/plural ("violão" x "violões", "guitarra" x "guitarras").
    alvo = {_radical(p) for p in normalizar(categoria).split() if len(p) > 2}
    mascara = cats["busca"].apply(lambda nome: bool(alvo & {_radical(p) for p in re.findall(r"\w+", nome)}))
    return cats.loc[mascara, "category_id"].tolist()


def _radical(palavra: str) -> str:
    for sufixo in ("oes", "aes", "ao"):  # violão/violões, pão/pães
        if palavra.endswith(sufixo):
            return palavra[: -len(sufixo)]
    return palavra.removesuffix("s")  # guitarra/guitarras, ukulele/ukuleles


def buscar_produtos(
    termo: str | None = None,
    categoria: str | None = None,
    preco_max: float | None = None,
    preco_min: float | None = None,
    apenas_disponiveis: bool = True,
    limite: int = 10,
) -> list[dict]:
    """Busca produtos por palavras do nome/descrição, categoria e faixa de preço.

    O filtro de preço considera o preço efetivo (promocional, se houver promoção ativa).
    """
    df = carregar_dados()["produtos"]

    if categoria:
        ids = _resolver_categoria(categoria)
        df = df[df["category_id"].isin(ids)]

    if termo:
        palavras = normalizar(termo).split()
        # Primeiro tenta casar todas as palavras no nome; se nada aparecer, amplia para a descrição.
        no_nome = df[df["busca_nome"].apply(lambda n: all(p in n for p in palavras))]
        df = no_nome if not no_nome.empty else df[df["busca_texto"].apply(lambda t: all(p in t for p in palavras))]

    preco_efetivo = df["preco_promocional"].fillna(df["price_brl"])
    if preco_max is not None:
        df = df[preco_efetivo <= preco_max]
        preco_efetivo = preco_efetivo.loc[df.index]
    if preco_min is not None:
        df = df[preco_efetivo >= preco_min]

    if apenas_disponiveis:
        df = df[df["disponivel"]]

    df = df.assign(_preco=df["preco_promocional"].fillna(df["price_brl"])).sort_values("_preco")
    return [_produto_para_dict(linha) for _, linha in df.head(limite).iterrows()]


def detalhes_produto(nome_ou_id: str | int) -> dict | None:
    """Detalhes completos de um produto, buscando por ID ou por nome (aproximado)."""
    df = carregar_dados()["produtos"]

    if str(nome_ou_id).strip().isdigit():
        achado = df[df["product_id"] == int(nome_ou_id)]
    else:
        palavras = normalizar(str(nome_ou_id)).split()
        achado = df[df["busca_nome"].apply(lambda n: all(p in n for p in palavras))]

    if achado.empty:
        return None
    if len(achado) > 1:
        return {
            "ambiguo": True,
            "mensagem": "Mais de um produto corresponde à busca; peça ao cliente para especificar.",
            "opcoes": [_produto_para_dict(linha) for _, linha in achado.head(5).iterrows()],
        }

    linha = achado.iloc[0]
    resultado = _produto_para_dict(linha, completo=True)
    if not linha["disponivel"]:
        resultado["alternativas"] = _alternativas(linha)
    return resultado


def _alternativas(linha: pd.Series, limite: int = 3) -> list[dict]:
    """Produtos disponíveis da mesma categoria com preço mais próximo (política 7.3)."""
    df = carregar_dados()["produtos"]
    candidatos = df[
        (df["category_id"] == linha["category_id"])
        & (df["disponivel"])
        & (df["product_id"] != linha["product_id"])
    ]
    distancia = (candidatos["price_brl"] - linha["price_brl"]).abs()
    proximos = candidatos.loc[distancia.sort_values().index].head(limite)
    return [_produto_para_dict(l) for _, l in proximos.iterrows()]


def status_pedido(order_id: int | str, email_ou_telefone: str) -> dict:
    """Status de um pedido, liberado apenas se o contato bater com o cliente do pedido (LGPD)."""
    dados = carregar_dados()
    pedidos, clientes, itens, produtos = dados["pedidos"], dados["clientes"], dados["itens"], dados["produtos"]

    if not str(order_id).strip().isdigit():
        return {"erro": "Número de pedido inválido."}
    pedido = pedidos[pedidos["order_id"] == int(order_id)]
    if pedido.empty:
        return {"erro": "Pedido não encontrado."}
    pedido = pedido.iloc[0]
    cliente = clientes[clientes["customer_id"] == pedido["customer_id"]].iloc[0]

    contato = str(email_ou_telefone).strip()
    if "@" in contato:
        confere = normalizar(contato) == cliente["email_norm"]
    else:
        digitos = apenas_digitos(contato)
        # Aceita o número com ou sem DDD.
        confere = len(digitos) >= 8 and cliente["telefone_digitos"].endswith(digitos)
    if not confere:
        # Mensagem genérica: não revela se o pedido existe para outra pessoa.
        return {"erro": "Não foi possível confirmar a identidade com os dados informados."}

    linhas_itens = itens[itens["order_id"] == pedido["order_id"]].merge(
        produtos[["product_id", "name"]], on="product_id", how="left"
    )

    resultado = {
        "pedido": int(pedido["order_id"]),
        "cliente_primeiro_nome": cliente["name"].split()[0],
        "data": pedido["order_date"],
        "status": STATUS_PEDIDO.get(pedido["status"], pedido["status"]),
        "total": float(pedido["total_brl"]),
        "pagamento": _forma_pagamento(pedido["payment_method"]),
        "itens": [
            {"produto": l["name"] if pd.notna(l["name"]) else f"produto {l['product_id']}", "quantidade": int(l["quantity"])}
            for _, l in linhas_itens.iterrows()
        ],
    }
    if pd.notna(pedido["tracking_code"]):
        resultado["codigo_rastreamento"] = pedido["tracking_code"]
    if pd.notna(pedido["estimated_delivery"]):
        resultado["previsao_entrega"] = pedido["estimated_delivery"]
    if pd.notna(pedido["notes"]):
        resultado["observacao"] = pedido["notes"]
    return resultado


def _forma_pagamento(codigo: str) -> str:
    if codigo in FORMA_PAGAMENTO:
        return FORMA_PAGAMENTO[codigo]
    parcelas = re.match(r"credit_(\d+)x", str(codigo))
    if parcelas:
        return f"cartão de crédito em {parcelas.group(1)}x"
    return str(codigo)


def listar_categorias() -> list[str]:
    return carregar_dados()["categorias"]["name"].tolist()


if __name__ == "__main__":
    from pprint import pprint

    print("== Violões disponíveis até R$ 1.000 ==")
    pprint(buscar_produtos(categoria="violões", preco_max=1000))
    print("\n== Takamine GD20 ==")
    pprint(detalhes_produto("takamine gd20"))
    print("\n== Produto sem estoque (Giannini GF-3D) ==")
    pprint(detalhes_produto(96))
    print("\n== Produto com promoção ativa (id 94) ==")
    pprint(detalhes_produto(94))
    print("\n== Pedido 8 com telefone certo ==")
    pprint(status_pedido(8, "(67) 99654-7821"))
    print("\n== Pedido 8 com e-mail errado ==")
    pprint(status_pedido(8, "fulano@jmail.com"))
