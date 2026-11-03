# 🐺 Lobisomem IA

Agentes de IA jogando Lobisomem entre si, com Python e Django.
Projeto de estudo: Python, Django, LLMs e agentes.

📚 Nunca mexeu com Python ou Django? Comece pelo [ESTUDOS.md](ESTUDOS.md).

## Rodando

```bash
uv venv --python 3.13 --managed-python   # cria o .venv (ou: python3.13 -m venv .venv)
source .venv/bin/activate
uv pip install -r requirements.txt        # (ou: pip install -r requirements.txt)

python manage.py migrate
python manage.py createsuperuser   # opcional, para usar o /admin
python manage.py runserver
```

Abra http://127.0.0.1:8000, escolha o tipo de agente, clique em **Nova partida** e use:
- **👁️ Modo deus**: mostra os papéis secretos, os eventos privados (votos dos lobos, investigação da vidente, proteção do médico) e o que cada agente *pensou*.
- **▶ Reproduzir**: reproduz a partida evento por evento, com a mesa reagindo.
- Partidas com IA rodam em segundo plano e a página atualiza **ao vivo**. No modo deus, aparece também a personalidade de cada jogador 🤖.

## Configurando a IA

Copie o `.env.example` para `.env` e escolha um provedor:

```bash
cp .env.example .env
```

| | Claude (API da Anthropic) | Ollama (local) |
|---|---|---|
| `.env` | `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY=...` | `LLM_PROVIDER=ollama` + `LLM_MODEL=llama3.1` |
| Onde conseguir | chave em console.anthropic.com (cobrada à parte da assinatura do Claude) | `brew install ollama`, `ollama serve` e `ollama pull llama3.1` |
| Custo | por uso | grátis |
| Qualidade | alta, segue as ferramentas certinho | depende do modelo; os pequenos erram mais |

O modelo padrão do Claude é o `claude-opus-5-5`, com `LLM_EFFORT=low` para as
respostas virem rápido. Uma partida de 8 jogadores faz em torno de 100 a 150
chamadas e leva alguns minutos. Para gastar menos, use `LLM_MODEL=claude-haiku-5-5`.

### Pelo terminal

```bash
python manage.py simular --seed 42           # uma partida
python manage.py simular --seed 42 --deus    # ...com os segredos
python manage.py simular --partidas 1000     # estatísticas de vitória
python manage.py simular --agente llm --deus  # partida com IA, ao vivo no terminal
python manage.py simular --agente misto       # metade IA, metade aleatórios
python manage.py test game                   # testes
```

## Como o projeto está organizado

```
game/
├── engine.py      ← REGRAS do jogo. Python puro, sem Django, sem IA.
├── agents.py      ← Quem DECIDE: RandomAgent e LLMAgent.
├── prompts.py     ← Como o jogo vira texto (e ferramentas) para a IA.
├── llm.py         ← Clientes de IA: Claude, Ollama e um falso para testes.
├── services.py    ← A PONTE: roda o engine e salva no banco.
├── models.py      ← Match, Player, GameEvent.
├── views.py       ← Telas (lista, nova partida, detalhe).
├── admin.py       ← Debug das partidas pelo /admin.
├── management/commands/simular.py
├── templates/ + static/   ← UI (CSS + JS puro)
└── tests/         ← test_engine.py, test_services.py e test_llm.py (sem chamar IA de verdade)
```

A separação é o principal ponto de estudo:

```
           ┌────────────┐   PlayerView    ┌──────────────┐
           │  engine.py │ ──────────────► │  agents.py   │
           │  (regras)  │ ◄────────────── │ (decisões)   │
           └─────┬──────┘     Action      └──────────────┘
                 │ on_event(Event)
                 ▼
           ┌────────────┐
           │ services.py│ ──► GameEvent no banco  (──► WebSocket na etapa 4)
           └────────────┘
```

- **`PlayerView`** é tudo o que um jogador consegue ver. O agente nunca recebe o estado completo, então não tem como "trapacear". Quando o agente virar um LLM, essa view vira o prompt.
- **`Action`** é a resposta do agente: `target` (um nome), `text` (a fala) e `thought` (o raciocínio, que só aparece no modo deus).
- **`Agent`** é um `Protocol`: qualquer classe com `night_action`, `speak` e `vote` serve. O motor não sabe se do outro lado tem um sorteio ou um LLM.
- **`Game._valid()`** ignora alvos inválidos. LLMs às vezes inventam nomes, e o jogo não pode quebrar por isso.
- **Seeds**: a mesma seed sempre gera a mesma partida. Ajuda muito a debugar.

## Linha de base

Com agentes aleatórios e 8 jogadores, **os lobos vencem ~79% das partidas**
(`simular --partidas 1000`). Isso é esperado: os aldeões votam quase no
escuro. Agentes com IA deveriam mudar esse número; medir isso é a etapa 6.

## Roteiro

- [x] **Etapa 1**: motor do jogo em Python puro + agentes aleatórios + testes
- [x] **Etapa 2**: models do Django, admin, telas, modo deus e replay
- [x] **Etapa 3**: `LLMAgent`
  - A `PlayerView` vira prompt (`prompts.py`): regras, papel secreto, personalidade e o histórico que o jogador viu
  - **Tool calling** com `strict`: as ferramentas `acao_noturna`, `falar` e `votar` têm um `enum` com os nomes válidos
  - Provedores trocáveis por configuração (`llm.py`): Claude ou Ollama
  - Se a IA falhar, o agente faz uma jogada aleatória e avisa no pensamento
  - Modos de partida: só aleatórios, só IA, ou misto
- [ ] **Etapa 4**: tempo real de verdade
  - Hoje a página consulta o servidor a cada 2s (polling) e a partida roda numa thread
  - Django Channels: o `save_event` em `services.py` envia o evento pelo WebSocket
  - Celery: rodar a partida numa fila de tarefas em vez de uma thread
- [ ] **Etapa 5**: jogador humano (um `HumanAgent` que espera a jogada vir da interface)
- [ ] **Etapa 6**: torneio, comparando modelos, prompts e personalidades em centenas de partidas

## Ideias para treinar Python antes da etapa 3

1. Adicione um papel novo, como o **Caçador**, que ao morrer leva alguém junto. Escreva o teste antes.
2. Proíba o médico de proteger a mesma pessoa duas noites seguidas.
3. Faça um `SmartAgent` sem IA que ganhe do `RandomAgent` (por exemplo, aldeões desconfiando de quem acusa a vidente).
4. Adicione um gráfico de "quem acusou quem" na tela da partida.
