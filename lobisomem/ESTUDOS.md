# 📚 Guia de estudos: Python e Django para quem vem do frontend

Este guia usa o próprio Lobisomem como material. Sempre que possível, cada
conceito aparece comparado ao equivalente no mundo JavaScript/TypeScript e
com um exemplo real tirado dos arquivos do projeto.

Sumário:

1. [Python para quem sabe JavaScript](#1-python-para-quem-sabe-javascript)
2. [O ecossistema: venv, uv, pip](#2-o-ecossistema-venv-uv-pip)
3. [Django: as peças](#3-django-as-peças)
4. [O caminho de uma requisição no projeto](#4-o-caminho-de-uma-requisição-no-projeto)
5. [Banco de dados: models, ORM e migrations](#5-banco-de-dados-models-orm-e-migrations)
6. [A arquitetura do Lobisomem](#6-a-arquitetura-do-lobisomem)
7. [Como funcionam os agentes com IA](#7-como-funcionam-os-agentes-com-ia)
8. [Ordem de leitura do código](#8-ordem-de-leitura-do-código)
9. [Comandos do dia a dia](#9-comandos-do-dia-a-dia)
10. [Exercícios](#10-exercícios)

---

## 1. Python para quem sabe JavaScript

### Indentação é sintaxe

Não existem `{ }` nem `;`. O bloco é definido pelo recuo (4 espaços).

```js
// JavaScript
function saudar(nome) {
  if (nome) {
    return `Olá, ${nome}`;
  }
  return "Olá!";
}
```

```python
# Python
def saudar(nome):
    if nome:
        return f"Olá, {nome}"
    return "Olá!"
```

### Tabela de equivalências

| JavaScript | Python |
|---|---|
| `const x = 1` / `let x = 1` | `x = 1` |
| `true`, `false`, `null`, `undefined` | `True`, `False`, `None` |
| `&&`, `\|\|`, `!` | `and`, `or`, `not` |
| `===` | `==` (e `is` para comparar com `None`/enums) |
| `[1, 2]` (array) | `[1, 2]` (list) |
| `{a: 1}` (objeto) | `{"a": 1}` (dict) |
| `new Set()` | `set()` |
| `arr.length` | `len(arr)` |
| `arr.push(x)` | `lista.append(x)` |
| `arr.map(x => x * 2)` | `[x * 2 for x in lista]` |
| `arr.filter(x => x > 0)` | `[x for x in lista if x > 0]` |
| `arr.includes(x)` | `x in lista` |
| `for (const x of arr)` | `for x in lista:` |
| `arr.forEach((x, i) => …)` | `for i, x in enumerate(lista):` |
| `Object.entries(obj)` | `obj.items()` |
| `` `Olá ${nome}` `` | `f"Olá {nome}"` |
| `cond ? a : b` | `a if cond else b` |
| `import { a } from "./b"` | `from .b import a` |
| `export` | não existe: tudo no módulo é importável |
| `console.log()` | `print()` |
| `try / catch / throw` | `try / except / raise` |
| `async / await` | `async / await` (igual!) |
| `// comentário` | `# comentário` |
| `/** doc */` | `"""docstring"""` |

### List comprehensions

É o jeito "pythônico" de fazer `map` e `filter`. Aparece em todo o projeto:

```python
# engine.py
return [p for p in self.players.values() if p.alive]
# JS: Object.values(this.players).filter(p => p.alive)
```

### Classes e `self`

`this` vira `self`, e ele é **sempre o primeiro parâmetro** dos métodos.
O construtor se chama `__init__`.

```python
class RandomAgent:
    def __init__(self, seed=None):          # constructor(seed)
        self.rng = random.Random(seed)      # this.rng = ...

    def vote(self, view):                   # vote(view)
        return self.rng.choice(view.alive)
```

Métodos que começam com `_` (como `_night`) são "privados" **por convenção**:
o Python não impede o acesso, é só um aviso para quem lê.

### Type hints: um TypeScript leve

```python
def vote(self, view: PlayerView) -> Action:
```

| TypeScript | Python |
|---|---|
| `string`, `number`, `boolean` | `str`, `int`/`float`, `bool` |
| `string \| null` | `str \| None` |
| `string[]` | `list[str]` |
| `Record<string, number>` | `dict[str, int]` |
| `interface` | `Protocol` |

A diferença importante: **o Python ignora os tipos na hora de rodar**. Eles
servem para o editor (autocomplete, alertas) e para ferramentas como `mypy`.

### Recursos usados no `engine.py`

- **Decorators (`@algo`)**: funções que "embrulham" outra função ou classe.
  `@dataclass` gera o construtor sozinho a partir dos atributos:

  ```python
  @dataclass
  class Action:
      target: str | None = None
      text: str = ""
  # Action(target="Ana", text="Foi ela!") já funciona.
  ```

- **`StrEnum`**: enum de strings, como o `enum` do TS. `Role.WEREWOLF == "lobisomem"`.
- **`@property`**: um método que se acessa como atributo (`role.team`, sem parênteses).
  É o `get` das classes JS.
- **`Protocol`**: uma interface. Qualquer classe com os métodos certos serve,
  sem precisar herdar nada. É o que permite trocar o agente aleatório pelo de IA.

---

## 2. O ecossistema: venv, uv, pip

| Mundo Node | Mundo Python |
|---|---|
| `npm`, `pnpm` | `pip`, `uv` |
| `package.json` | `requirements.txt` (ou `pyproject.toml`) |
| `node_modules/` | `.venv/` |
| `npm run dev` | `python manage.py runserver` |
| `npx algo` | `python -m algo` |
| Jest / Vitest | `unittest` / `pytest` |
| ESLint + Prettier | `ruff` |

### O ambiente virtual (`.venv`)

No Node, cada projeto tem o próprio `node_modules` automaticamente. No Python,
sem um ambiente virtual, tudo seria instalado globalmente. O `.venv` é uma
pasta com um Python e as bibliotecas só deste projeto.

```bash
source .venv/bin/activate     # "entra" no ambiente; o terminal mostra (.venv)
deactivate                    # sai
uv pip install requests       # instala no .venv (use no lugar de pip install)
uv pip freeze                 # lista o que está instalado
```

> Neste Mac, usamos o `uv` porque o Python do Homebrew veio com um defeito
> de compatibilidade com o macOS 26. O `uv` traz um Python próprio e completo.

---

## 3. Django: as peças

Django é um framework **completo** ("baterias inclusas"): banco de dados,
rotas, templates, autenticação, admin, formulários e testes vêm prontos.
É mais parecido com Next.js ou Rails do que com Express.

| Django | Analogia no mundo JS |
|---|---|
| Projeto (`config/`) | a configuração global (`next.config.js`) |
| App (`game/`) | um módulo/feature do projeto |
| `settings.py` | configurações + `.env` |
| `urls.py` | o roteador |
| **View** (`views.py`) | route handler / controller |
| **Model** (`models.py`) | schema do Prisma |
| Migrations | `prisma migrate` |
| **Template** (`.html`) | Handlebars / EJS (HTML gerado no servidor) |
| Admin (`/admin`) | um painel de banco pronto |
| `manage.py` | os scripts do `package.json` |

> ⚠️ Pegadinha de nome: no Django, **view** é a função que trata a
> requisição (o controller). O HTML é o **template**.

---

## 4. O caminho de uma requisição no projeto

O navegador pede `/partidas/2/`:

**1. `config/urls.py`**: repassa tudo para o app `game`.

```python
path("", include("game.urls")),
```

**2. `game/urls.py`**: encontra a rota e extrai o número (como `/partidas/:pk`).

```python
path("partidas/<int:pk>/", views.detail, name="detail"),
```

**3. `game/views.py`**: busca os dados e manda para o template.

```python
def detail(request, pk):
    match = get_object_or_404(Match, pk=pk)
    ...
    return render(request, "game/detail.html", {"match": match, ...})
```

Equivalente no Express:

```js
app.get("/partidas/:pk", async (req, res) => {
  const match = await db.match.findUnique({ where: { id: req.params.pk } });
  if (!match) return res.status(404).end();
  res.render("detail", { match });
});
```

**4. `templates/game/detail.html`**: HTML com a linguagem de template do Django.

```django
{% for p in players %}
  <div class="player">{{ p.name }}</div>
{% endfor %}
```

`{{ }}` imprime um valor, `{% %}` é lógica (`if`, `for`, `url`). Roda **no
servidor**: o navegador recebe HTML pronto. O JavaScript da página
(`static/game/match.js`) é JS normal, rodando no navegador.

### Outras peças que aparecem

- **`{% csrf_token %}`** nos formulários: proteção contra CSRF. Todo `<form method="post">` precisa.
- **`redirect(match)`**: redireciona usando o `get_absolute_url()` do model.
- **`messages.error(...)`**: mensagens "flash" que aparecem na próxima página.
- **`@require_POST`**: decorator que só aceita POST naquela view.

---

## 5. Banco de dados: models, ORM e migrations

Cada classe em `models.py` vira uma tabela; cada atributo vira uma coluna.

```python
class Player(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="players")
    name = models.CharField(max_length=40)
    alive = models.BooleanField(default=True)
```

- `ForeignKey` = relação "muitos para um" (vários jogadores numa partida).
- `related_name="players"` permite fazer `match.players.all()` do outro lado.
- `on_delete=CASCADE` = apagou a partida, apaga os jogadores.

### Consultando sem escrever SQL (o ORM)

| Django ORM | Prisma |
|---|---|
| `Match.objects.all()` | `prisma.match.findMany()` |
| `Match.objects.get(pk=2)` | `findUniqueOrThrow({ where: { id: 2 } })` |
| `Match.objects.filter(winner="aldeia")` | `findMany({ where: { winner: "aldeia" } })` |
| `Match.objects.create(seed=1)` | `create({ data: { seed: 1 } })` |
| `match.players.filter(alive=True)` | `findMany({ where: { matchId, alive: true } })` |
| `.count()`, `.exists()`, `.order_by("-created_at")` | `count()`, …, `orderBy` |

Filtros com dois underlines: `Player.objects.filter(match__winner="aldeia")`
segue a relação (jogadores de partidas que a aldeia venceu).

### Migrations

Toda vez que mudar um model:

```bash
python manage.py makemigrations   # gera o arquivo em game/migrations/
python manage.py migrate          # aplica no banco
```

Os arquivos de migration **vão para o Git**. O `db.sqlite3` não.

---

## 6. A arquitetura do Lobisomem

```
game/
├── engine.py      ← REGRAS do jogo. Python puro, sem Django.
├── agents.py      ← Quem DECIDE: RandomAgent e LLMAgent.
├── llm.py         ← Clientes de IA (Claude, Ollama) com a mesma interface.
├── prompts.py     ← Como a situação do jogo vira texto para a IA.
├── services.py    ← A PONTE: roda o engine e salva no banco.
├── models.py      ← Match, Player, GameEvent.
├── views.py, urls.py, templates/, static/   ← a parte web.
└── tests/
```

A regra de ouro: **o motor não sabe nada de Django nem de IA**.

```
           ┌────────────┐   PlayerView    ┌──────────────┐
           │  engine.py │ ──────────────► │  agents.py   │
           │  (regras)  │ ◄────────────── │ (decisões)   │
           └─────┬──────┘     Action      └──────────────┘
                 │ on_event(Event)
                 ▼
           ┌────────────┐
           │ services.py│ ──► GameEvent no banco
           └────────────┘
```

- **`PlayerView`**: tudo o que **um** jogador consegue ver. O agente nunca
  recebe o estado completo, então não tem como trapacear.
- **`Action`**: a resposta do agente (`target`, `text`, `thought`).
- **`Event`**: tudo o que acontece vira um evento, com uma `visibility`
  (público, só lobos, ou só um jogador). O modo deus mostra todos.
- **Seed**: a mesma seed gera a mesma partida (com agentes aleatórios).

---

## 7. Como funcionam os agentes com IA

Um LLM não "joga": ele recebe texto e devolve texto. O trabalho do
`LLMAgent` é traduzir o jogo para texto e a resposta de volta para o jogo.

```
PlayerView ──► prompts.py ──► mensagens ──► LLM ──► chamada de ferramenta ──► Action
                (texto)                              votar(alvo="Ana", ...)
```

1. **System prompt**: as regras, o papel secreto do jogador e a personalidade.
2. **Mensagem do usuário**: o que ele viu até agora (o histórico da
   `PlayerView`) e o que precisa fazer agora.
3. **Tool calling**: em vez de pedir "responda em JSON", oferecemos uma
   *ferramenta* (`votar`, `falar`, `acao_noturna`) com um schema. O modelo
   "chama" a ferramenta com argumentos estruturados, e o código lê esses
   argumentos. É muito mais confiável do que interpretar texto livre.
4. **Validação**: se o modelo inventar um nome, o `Game._valid()` ignora.
   Se a API falhar, o `LLMAgent` cai para uma jogada aleatória e registra o
   erro no pensamento. O jogo nunca quebra por causa da IA.

O campo `pensamento` da ferramenta é o que aparece no **modo deus**.

---

## 8. Ordem de leitura do código

1. `game/engine.py`: comece pelos tipos no topo e depois `_night`, `_discussion`, `_vote`.
2. `game/agents.py`: o `RandomAgent` primeiro, depois o `LLMAgent`.
3. `game/tests/test_engine.py`: os testes descrevem cada regra.
4. `game/models.py` → `urls.py` → `views.py` → `templates/`: o caminho da requisição.
5. `game/services.py`: a ponte.
6. `game/prompts.py` e `game/llm.py`: a parte de IA.

---

## 9. Comandos do dia a dia

```bash
cd lobisomem
source .venv/bin/activate

python manage.py runserver            # servidor em http://127.0.0.1:8000
python manage.py test game            # testes
python manage.py shell                # Python com o projeto carregado
python manage.py makemigrations       # depois de mudar models.py
python manage.py migrate
python manage.py createsuperuser      # para entrar no /admin

python manage.py simular --seed 42 --deus
python manage.py simular --partidas 500
python manage.py simular --agente llm --deus      # partida com IA
```

### Brincando no shell

```python
from game.models import Match, Player
Match.objects.count()
m = Match.objects.first()
[p.name for p in m.players.filter(alive=True)]
m.events.filter(kind="fala").values_list("actor", "content")[:5]
```

### Debugando

- Coloque `breakpoint()` em qualquer linha. Quando o código passar por ali, o
  terminal vira um debugger: `p variavel` imprime, `n` avança, `c` continua.
- Ou use o debugger do VS Code (extensão Python) com breakpoints no editor.

---

## 10. Exercícios

Em ordem de dificuldade. Para cada um, **escreva o teste primeiro** em
`game/tests/test_engine.py`.

1. **Python básico**: crie uma função em `engine.py` que devolve quantos
   jogadores de cada papel estão vivos (dica: `collections.Counter`).
2. **Regra nova**: o médico não pode proteger a mesma pessoa duas noites seguidas.
3. **Papel novo, o Caçador**: ao morrer, leva alguém junto. Mexe no enum
   `Role`, na distribuição de papéis e nas fases.
4. **Django**: adicione um campo `duration_ms` em `Match` (quanto tempo a
   partida levou). Model → `makemigrations` → `migrate` → mostrar na tela.
5. **Django + frontend**: uma página `/estatisticas/` com a taxa de vitória
   de cada time e de cada tipo de agente, usando o ORM.
6. **IA**: mude as personalidades em `prompts.py` e compare, com
   `simular --partidas`, se alguma faz a aldeia ganhar mais.
