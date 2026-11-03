**Cliente:** Oi, quero saber onde está meu pedido

**Toninho:** Olá! Tudo bem? Para eu conseguir localizar o seu pedido e te passar o status certinho, eu preciso de duas informações:

*   O **número do pedido**
*   O **e-mail ou telefone** que você cadastrou na hora da compra.

Pode me passar esses dados, por favor? Assim que você enviar, eu já consulto aqui para você!

**Cliente:** É o pedido 8

**Toninho:** Com certeza! Já anotei o número do pedido (8).

Agora, só falta você me informar o **e-mail ou o telefone** que usou no cadastro da compra. É uma medida de segurança para eu poder acessar os detalhes para você.

Fico no aguardo!

**Cliente:** Meu e-mail é ana.ferreira@gmail.com

> 🔧 `get_order_status({"email_or_phone": "ana.ferreira@gmail.com", "order_id": "8"})`

**Toninho:** Oi, Ana! Poxa, tentei consultar aqui, mas os dados não bateram no meu sistema. 😕

Poderia conferir se o número do pedido está certinho ou se o e-mail cadastrado foi outro? Às vezes pode ter sido um telefone também.

Fico aqui esperando para tentar de novo!

**Cliente:** Ah, desculpa, usei o telefone (67) 99654-7821

> 🔧 `get_order_status({"email_or_phone": "(67) 99654-7821", "order_id": "8"})`

**Toninho:** Oi, Ana! Agora sim, consegui localizar! 😊

Aqui estão os detalhes do seu pedido:

*   **Pedido:** #8
*   **Item:** 1x Ukulele Kala KA-C Concert Mogno
*   **Status:** Enviado (shipped) 🚚
*   **Código de Rastreio:** BRJL5544332BR
*   **Previsão de Entrega:** 28/02/2026

Falta pouco para o seu ukulele chegar! Posso te ajudar com mais alguma coisa?
