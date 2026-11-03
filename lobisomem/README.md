# 🐺 Lobisomem IA

Agentes de IA jogando Lobisomem entre si, com Python e Django.
Projeto de estudo: Python, Django, e depois LLMs e agentes.

## Rodando

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser   # opcional, para usar o /admin
python manage.py runserver
```

Abra http://127.0.0.1:8000, clique em **Nova partida** e use:
- **👁️ Modo deus**: mostra os papéis secretos, os eventos privados (votos dos lobos, investigação da vidente, proteção do médico) e o que cada agente *pensou*.
- **▶ Reproduzir**: reproduz a partida evento por evento, com a mesa reagindo.

### Pelo terminal

```bash
python manage.py simular --seed 42           # uma partida
python manage.py simular --seed 42 --deus    # ...com os segredos
python manage.py simular --partidas 1000     # estatísticas de vitória
python manage.py test game                   # testes
```

## Como o projeto está organizado

```
game/
├── engine.py      ← REGRAS do jogo. Python puro, sem Django, sem IA.
├── agents.py      ← Quem DECIDE. Hoje: RandomAgent. Amanhã: LLMAgent.
├── services.py    ← A PONTE: roda o engine e salva no banco.
├── models.py      ← Match, Player, GameEvent.
├── views.py       ← Telas (lista, nova partida, detalhe).
├── admin.py       ← Debug das partidas pelo /admin.
├── management/commands/simular.py
├── templates/ + static/   ← UI (CSS + JS puro)
└── tests/         ← test_engine.py (rápido, sem banco) e test_services.py
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
escuro. O objetivo da etapa 3 é fazer agentes LLM que mudem esse número.

## Roteiro

- [x] **Etapa 1**: motor do jogo em Python puro + agentes aleatórios + testes
- [x] **Etapa 2**: models do Django, admin, telas, modo deus e replay
- [ ] **Etapa 3**: `LLMAgent`
  - Transformar a `PlayerView` em prompt (papel, quem está vivo, histórico visível)
  - Usar **tool calling** (`votar(jogador)`, `investigar(jogador)`…) ou saída estruturada para devolver uma `Action`
  - Dar uma personalidade a cada agente (o campo `Player.personality` já existe)
  - Registrar em `AGENT_REGISTRY["llm"]` e misturar agentes aleatórios e LLM na mesma partida
- [ ] **Etapa 4**: tempo real
  - Django Channels: o `save_event` em `services.py` também envia o evento pelo WebSocket
  - Celery: rodar `game.step()` em background, fase por fase
- [ ] **Etapa 5**: jogador humano (um `HumanAgent` que espera a jogada vir da interface)
- [ ] **Etapa 6**: torneio, comparando modelos, prompts e personalidades em centenas de partidas

## Ideias para treinar Python antes da etapa 3

1. Adicione um papel novo, como o **Caçador**, que ao morrer leva alguém junto. Escreva o teste antes.
2. Proíba o médico de proteger a mesma pessoa duas noites seguidas.
3. Faça um `SmartAgent` sem IA que ganhe do `RandomAgent` (por exemplo, aldeões desconfiando de quem acusa a vidente).
4. Adicione um gráfico de "quem acusou quem" na tela da partida.
