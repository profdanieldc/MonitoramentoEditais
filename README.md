# Monitor de editais

Coleta editais uma ou duas vezes por dia, avisa no Telegram o que é novo ou
foi retificado, e mantém um portal para consulta. Roda inteiramente no
GitHub, sem servidor e sem custo.

Nesta primeira versão há uma fonte ativa: **STED/UFMA**. FAPEMA e SECTI-MA
entram em seguida, no mesmo esqueleto.

## Como isso funciona

O repositório é o banco de dados. A cada rodada, o GitHub Actions executa o
coletor, compara o resultado com `docs/editais.json` e grava um commit com o
que mudou. O portal em GitHub Pages lê esse mesmo arquivo.

Três decisões que valem entender, porque explicam o código:

**A chave de um edital é a URL, nunca a data.** Na listagem da STED, um
edital antigo que sofre qualquer alteração salta para o topo. Se a data
fosse a chave, ele apareceria como novidade toda vez.

**Retificação é diferente de novidade.** Se título, descrição, data de
modificação ou prazo mudarem, a revisão sobe e o edital volta a aparecer —
inclusive se você já tiver arquivado ele. Arquivar não pode virar um jeito de
perder justamente a mudança que importava.

**A pontuação ordena, nunca descarta.** Todo edital coletado aparece no
portal. O que a pontuação decide é a ordem da lista e o que merece
interromper seu dia via Telegram.

## Instalação

Cinco passos, todos pelo navegador. Nenhum exige linha de comando.

### 1. Criar o repositório

No GitHub, crie um repositório **público** (o Actions só é gratuito sem
limite em repositórios públicos) e envie estes arquivos para ele. Pela
interface: **Add file → Upload files**, arraste tudo, e confirme em
*Commit changes*.

### 2. Criar o bot do Telegram

No Telegram, converse com o **@BotFather**, mande `/newbot` e siga as
perguntas. No fim ele devolve um token parecido com
`8123456789:AAF...`. Guarde.

Depois mande qualquer mensagem para o seu bot recém-criado (isso é
necessário: bots não conseguem iniciar conversa). Em seguida abra no
navegador:

```
https://api.telegram.org/bot SEU_TOKEN /getUpdates
```

sem os espaços. Procure no resultado o campo `"chat":{"id":123456789`.
Esse número é o seu chat_id.

### 3. Guardar token e chat_id

No repositório: **Settings → Secrets and variables → Actions →
New repository secret**. Crie dois:

| Nome | Valor |
|---|---|
| `TELEGRAM_TOKEN` | o token do BotFather |
| `TELEGRAM_CHAT_ID` | o número do chat |

Guardados como secrets, eles não aparecem no código nem nos logs.

### 4. Ligar o portal

**Settings → Pages**. Em *Source* escolha **Deploy from a branch**, e
selecione a branch `main` com a pasta `/docs`. Em poucos minutos o portal
fica em `https://SEU-USUARIO.github.io/NOME-DO-REPO/`.

### 5. Rodar pela primeira vez

**Actions → Coletar editais → Run workflow**. A primeira rodada vai
encontrar tudo como novidade, então o Telegram recebe uma mensagem cheia.
É esperado; a partir da segunda, só chega o que for realmente novo.

Se a aba Actions pedir para você habilitar workflows, confirme.

O `docs/editais.json` que veio junto é uma amostra de demonstração, com
títulos reais da STED e prazos fictícios, só para você conferir se o portal
está no ar antes da primeira coleta. A primeira rodada substitui o arquivo
inteiro por dados reais.

## Ajustar o que chega

Tudo que define seus interesses está em `config/perfis.yaml`. Termos com
peso positivo sobem o edital na lista; peso negativo rebaixa. Só o que
passar do `limiar_alerta` vira mensagem no Telegram — o resto continua
visível no portal.

Se um tipo de aviso encher o alerta sem valer a pena — como as
"prorrogação da validade do resultado" da STED — acrescente o termo em
`rebaixar` com peso negativo. Você ensina uma vez em vez de arquivar o
mesmo tipo de item toda semana.

Depois de duas semanas de uso vale revisar esses pesos com dado real. Antes
disso é chute.

## Adicionar fontes

`config/fontes.yaml`. Qualquer setor da UFMA hospedado no mesmo Plone usa o
coletor que já existe: basta um bloco novo com `tipo: plone` e a URL da
coleção. O arquivo já traz o PROPESQ como exemplo, desativado.

FAPEMA e SECTI precisam de coletores próprios, que entram na próxima etapa.

## Arquivar e salvar

O portal guarda esses estados no seu navegador (localStorage), então valem
por dispositivo: o que você arquivar no notebook não aparece arquivado no
celular. Foi uma escolha deliberada para não exigir token de escrita nem
banco de dados. Como o alerta chega pelo Telegram, o portal serve mais para
consulta, e a falta de sincronia incomoda pouco.

Editais com prazo vencido saem sozinhos da aba *Abertos*, sem precisar de
clique.

## Rodar no seu computador

Opcional, útil para testar mudanças nos pesos antes de subir:

```bash
pip install -r requirements.txt
python executar.py --sem-alerta       # coleta sem mandar mensagem
python executar.py --fonte sted-ufma  # só uma fonte
python teste_local.py                 # valida a lógica sem acessar a rede
```

## Limites conhecidos

- **O prazo nem sempre é identificado.** O coletor procura a data de
  encerramento no texto da página, mas há editais em que ela só existe
  dentro do PDF. Nesses casos o portal mostra "prazo não identificado" em
  vez de inventar uma data, e o link continua lá.
- **Coletores quebram quando o site muda de layout.** Por isso existe o
  aviso de silêncio: se uma fonte passa sete dias sem retornar nada, o
  portal e o Telegram avisam. Sem isso, um coletor morre calado e você só
  descobre ao perder um prazo.
- **O Actions pode atrasar.** O agendamento do GitHub não é pontual; atrasos
  de alguns minutos a uma hora em horário de pico são normais.
