# excalidraw-cli (excli)

CLI для управления Excalidraw-канвасом из терминала. Для людей и AI-агентов.

Рисуй диаграммы одной командой, описывай архитектуру в YAML, управляй канвасом через скрипты — или дай это делать AI-агенту (Claude Code, Cursor, Codex CLI).

---

## Оглавление

- [Быстрый старт](#быстрый-старт)
- [Команды](#команды)
- [YAML-диаграммы](#yaml-диаграммы-excliyaml)
- [Кастомизация с помощью AI-агентов](#кастомизация-с-помощью-ai-агентов)
- [Продвинутое использование](#продвинутое-использование)
- [Примеры](#примеры)
- [Установка canvas-сервера](#установка-canvas-сервера)
- [Лицензия](#лицензия)

---

## Быстрый старт

### 1. Запусти canvas-сервер

```bash
docker run -d -p 3000:3000 --name excalidraw-canvas ghcr.io/yctimlin/mcp_excalidraw-canvas:latest
```

Открой http://localhost:3000 в браузере — увидишь пустой Excalidraw-канвас.

### 2. Установи excli

```bash
pip install git+https://github.com/ArtemArzi/excalidraw-cli.git
```

Или локально:

```bash
git clone https://github.com/ArtemArzi/excalidraw-cli.git
cd excalidraw-cli
pip install -e .
```

### 3. Проверь

```bash
excli health
```

Если видишь `status: ok` — всё работает. Теперь можно рисовать:

```bash
excli flow "Идея -> Прототип -> Продукт"
```

Переключись в браузер — на канвасе появился флоучарт.

---

## Команды

### Основные

| Команда | Что делает | Пример |
|---------|-----------|--------|
| `flow` | Создаёт флоучарт из текста | `excli flow "A -> B -> C"` |
| `box` | Создаёт блок с текстом | `excli box "Сервер" --at 100,200` |
| `text` | Добавляет текст | `excli text "Заметка" --at 300,100` |
| `connect` | Соединяет два элемента стрелкой | `excli connect ID1 ID2 --label "данные"` |
| `render` | Рисует диаграмму из YAML-файла | `excli render diagram.excli.yaml` |
| `mermaid` | Конвертирует Mermaid-диаграмму | `excli mermaid "graph LR; A-->B"` |

### Управление канвасом

| Команда | Что делает | Пример |
|---------|-----------|--------|
| `list` | Список всех элементов | `excli list` |
| `describe` | Описание содержимого канваса | `excli describe` |
| `delete` | Удаляет элемент по ID | `excli delete ELEMENT_ID` |
| `clear` | Очищает весь канвас | `excli clear --yes` |
| `zoom` | Управление viewport | `excli zoom --fit` |

### Экспорт и импорт

| Команда | Что делает | Пример |
|---------|-----------|--------|
| `export` | Экспорт в PNG/SVG | `excli export png diagram.png` |
| `scene import` | Импорт .excalidraw файла на канвас | `excli scene import file.excalidraw` |
| `scene export` | Экспорт канваса в .excalidraw файл | `excli scene export file.excalidraw` |
| `snapshot save` | Сохранить состояние канваса | `excli snapshot save "before-changes"` |
| `snapshot restore` | Восстановить состояние | `excli snapshot restore "before-changes"` |
| `snapshot list` | Список снапшотов | `excli snapshot list` |

### Редактирование YAML-диаграмм

| Команда | Что делает | Пример |
|---------|-----------|--------|
| `node add` | Добавить ноду в YAML | `excli node add db "PostgreSQL" --in diagram.excli.yaml` |
| `node remove` | Удалить ноду | `excli node remove db --in diagram.excli.yaml` |
| `edge add` | Добавить связь | `excli edge add api db --in diagram.excli.yaml` |
| `edge remove` | Удалить связь | `excli edge remove api db --in diagram.excli.yaml` |

### Флаги

| Флаг | Где работает | Что делает |
|------|-------------|-----------|
| `--json` | Все команды | Вывод в JSON (для скриптов и агентов) |
| `--at X,Y` | `box`, `text` | Координаты размещения |
| `--bg COLOR` | `box` | Цвет фона |
| `--shape` | `box` | Форма: `rectangle`, `ellipse`, `diamond` |
| `--size WxH` | `box` | Размер (авто, если не указан) |
| `--direction` | `flow` | Направление: `horizontal` / `vertical` |
| `--palette` | `flow` | Палитра: `default`, `mono`, `warm`, `cool` |
| `--clear` | `flow` | Очистить канвас перед рисованием |
| `--replace` | `render` | Очистить канвас перед рендером |
| `--dry-run` | `render` | Показать layout без рендера |
| `--merge` | `scene import` | Добавить к существующему, а не заменить |
| `--label` | `connect`, `edge add` | Подпись на стрелке |

---

## YAML-диаграммы (.excli.yaml)

Самая мощная фича excli — декларативные диаграммы. Описываешь структуру в YAML, excli сам раскладывает по канвасу с auto-layout.

### Минимальный пример

```yaml
title: "Простой процесс"
nodes:
  start:
    text: "Начало"
    style: green
  process:
    text: "Обработка"
    style: blue
  end:
    text: "Готово"
    style: yellow
edges:
  - [start, process]
  - [process, end]
```

```bash
excli render simple-flow.excli.yaml --replace
```

### Формат файла

```yaml
# Заголовок диаграммы (необязательно)
title: "Название"

# Ноды — ключ: свойства
nodes:
  node_key:
    text: "Текст внутри блока"
    style: blue          # цвет фона (см. палитру ниже)
    shape: rectangle     # rectangle | ellipse | diamond
    size: normal         # small | normal | large

# Связи — [откуда, куда] или [откуда, куда, {опции}]
edges:
  - [node_a, node_b]
  - [node_a, node_c, {label: "подпись", color: "red"}]

# Боковые связи — пунктирные, не влияют на layout
side:
  - {from: node_b, to: external, text: "API call", color: gray}

# Заметки — блок под диаграммой
notes:
  - "Первая заметка"
  - "Вторая заметка"
```

### Палитра стилей

| Стиль | Цвет | Hex |
|-------|------|-----|
| `blue` | Голубой | `#a5d8ff` |
| `green` | Зелёный | `#b2f2bb` |
| `yellow` | Жёлтый | `#ffec99` |
| `orange` | Оранжевый | `#ffd8a8` |
| `red` | Красный | `#ffa8a8` |
| `pink` | Розовый | `#fcc2d7` |
| `purple` | Фиолетовый | `#d0bfff` |
| `violet` | Сиреневый | `#eebefa` |
| `cyan` | Бирюзовый | `#99e9f2` |
| `mint` | Мятный | `#c3fae8` |
| `gray` | Серый | `#e9ecef` |
| `lime` | Лаймовый | `#c0eb75` |

### Палитры для flow

| Палитра | Описание |
|---------|----------|
| `default` | Яркие разноцветные блоки |
| `mono` | Оттенки серого |
| `warm` | Тёплые тона (оранжевый, розовый, сиреневый) |
| `cool` | Холодные тона (голубой, зелёный, мятный) |

### Размеры

| Размер | Шрифт | Мин. ширина | Мин. высота |
|--------|-------|-------------|-------------|
| `small` | 14px | 100 | 40 |
| `normal` | 18px | 140 | 55 |
| `large` | 22px | 180 | 70 |

Если размер не указан, блок автоматически подстраивается под текст.

### Инкрементальное редактирование

Не нужно переписывать весь YAML — добавляй ноды и связи из терминала:

```bash
# Добавить ноду и сразу связать
excli node add cache "Redis" --in arch.excli.yaml --style orange --connect-from api

# Удалить связь
excli edge remove api old_service --in arch.excli.yaml

# Перерендерить
excli render arch.excli.yaml --replace
```

### Auto-layout

excli автоматически раскладывает ноды:
- **Топологическая сортировка** — ноды упорядочены слева направо по зависимостям
- **Cycle-breaking** — если есть циклы, они разрываются для layout (стрелки остаются)
- **Вертикальное центрирование** — ноды в каждом слое центрированы
- **Минимизация пересечений** — используется медианная эвристика

---

## Кастомизация с помощью AI-агентов

excli создан для работы в паре с AI-агентами. Агент может рисовать диаграммы, редактировать их, экспортировать — всё через CLI.

### Claude Code

#### Настройка

Добавь в `CLAUDE.md` своего проекта:

```markdown
## Excalidraw workflow
- Для визуализации используй `excli` (CLI для Excalidraw).
- Canvas-сервер: запусти `docker run -d -p 3000:3000 --name excalidraw-canvas ghcr.io/yctimlin/mcp_excalidraw-canvas:latest`
- Открой http://localhost:3000 в браузере.
- Для сложных диаграмм: создай `.excli.yaml` + `excli render --replace`
- Для быстрых флоу: `excli flow "A -> B -> C"`
- Для совместной работы: `excli scene import/export`
- Экспорт: `excli export png output.png`
```

#### Примеры промптов

После настройки можно просто просить Claude Code:

```
Нарисуй архитектуру нашего бэкенда на Excalidraw
```

```
Добавь ноду "Redis Cache" в диаграмму arch.excli.yaml и соедини с API
```

```
Покажи процесс CI/CD пайплайна в виде флоучарта
```

```
Экспортни текущий канвас в PNG
```

Claude Code будет использовать excli команды для выполнения.

#### Расширение excli через Claude Code

Claude Code может не только использовать excli, но и **расширять его**. Примеры:

**Добавить новую команду:**
```
Добавь в excli команду `excli template list` — показывает список .excli.yaml шаблонов из папки ~/.excli/templates/
```

**Добавить новый стиль:**
```
Добавь в палитру excli стиль "corporate" с цветами нашего бренда: primary #2563eb, secondary #7c3aed, accent #f59e0b
```

**Создать YAML-шаблон:**
```
Создай шаблон .excli.yaml для типичной микросервисной архитектуры: API Gateway, Auth, 3 сервиса, БД, очередь
```

**Добавить интеграцию:**
```
Добавь в excli команду `excli from-markdown` — парсит маркдаун-список и рисует из него дерево
```

Весь код excli — открытый Python с Click. Claude Code может читать исходники, понимать структуру и добавлять фичи.

#### Структура кода для расширения

```
excli/
├── cli.py        ← сюда добавлять новые @cli.command()
├── backend.py    ← HTTP-клиент, менять не нужно
├── elements.py   ← билдеры элементов (make_box, make_arrow)
├── flow.py       ← логика "A -> B -> C", палитры
└── diagram.py    ← YAML-движок, auto-layout
```

Чтобы добавить новую команду — достаточно написать функцию в `cli.py` с декоратором `@cli.command()`. Вся работа с канвасом идёт через `backend.py` (HTTP-запросы к серверу) и `elements.py` (создание элементов).

#### Skill для Claude Code

Можно создать скилл, который научит Claude Code продвинутым паттернам работы с excli. Положи файл в `.claude/skills/excli-skill.md`:

```markdown
---
name: excli
description: Управление Excalidraw-канвасом через CLI
---

## Команды excli

### Быстрый флоу
excli flow "Шаг 1 -> Шаг 2 -> Шаг 3"

### Сложная диаграмма
1. Создай .excli.yaml с нодами и связями
2. excli render diagram.excli.yaml --replace

### Совместная работа
1. excli scene export diagram.excalidraw  — выгрузить канвас
2. Человек редактирует в браузере (excalidraw.com или localhost:3000)
3. excli scene import diagram.excalidraw  — загрузить обратно
4. Дорисовать через excli
5. excli scene export diagram.excalidraw  — сохранить

### Безопасность
- Перед большими изменениями: excli snapshot save "before-changes"
- Если что-то пошло не так: excli snapshot restore "before-changes"

### --json режим
Для парсинга вывода используй --json:
excli --json list
excli --json describe
```

### Cursor

Cursor работает через MCP-сервер напрямую. excli CLI не нужен — Cursor вызывает MCP-инструменты.

#### Настройка MCP-сервера

Создай `.cursor/mcp.json` в проекте:

```json
{
  "mcpServers": {
    "excalidraw": {
      "command": "node",
      "args": ["/path/to/mcp_excalidraw/dist/index.js"],
      "env": {
        "EXPRESS_SERVER_URL": "http://localhost:3000",
        "ENABLE_CANVAS_SYNC": "true"
      }
    }
  }
}
```

Или через Docker:

```json
{
  "mcpServers": {
    "excalidraw": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "EXPRESS_SERVER_URL=http://host.docker.internal:3000",
        "-e", "ENABLE_CANVAS_SYNC=true",
        "ghcr.io/yctimlin/mcp_excalidraw:latest"
      ]
    }
  }
}
```

После этого Cursor получает доступ к 26 MCP-инструментам: create_element, update_element, describe_scene, export_scene и т.д.

#### Когда excli полезен вместе с Cursor

Даже при работе через MCP, excli полезен для:
- **YAML-диаграммы** — MCP не умеет auto-layout, excli умеет
- **Batch-операции** — `excli render` за один вызов создаёт десятки элементов
- **Скрипты и CI** — excli работает из bash, MCP — нет

### Codex CLI

```bash
codex mcp add excalidraw \
  --env EXPRESS_SERVER_URL=http://localhost:3000 \
  --env ENABLE_CANVAS_SYNC=true \
  -- node /path/to/mcp_excalidraw/dist/index.js
```

### Другие AI-агенты

Любой агент, который умеет вызывать shell-команды, может использовать excli. Достаточно:

1. Запустить canvas-сервер
2. Установить excli
3. Дать агенту инструкцию: "для визуализации используй команду excli"

Режим `--json` делает вывод машиночитаемым — агент может парсить результаты.

### Совместная работа человек + AI

Типичный цикл:

```
AI-агент                          Человек
    │                                │
    ├── excli render arch.yaml ──►   │
    │                                ├── открывает localhost:3000
    │                                ├── двигает блоки, правит текст
    │                                ├── Save to disk (.excalidraw)
    │   ◄── excli scene import ──────┤
    ├── дорисовывает через excli     │
    ├── excli scene export ──────►   │
    │                                ├── проверяет результат
    │                                └── ок!
```

#### Протокол

1. **AI рисует** — через `excli render`, `excli flow`, `excli box` и т.д.
2. **Человек правит в браузере** — перетаскивает блоки, меняет текст, добавляет элементы
3. **AI забирает правки** — `excli scene import file.excalidraw`
4. **AI дорабатывает** — точечные изменения через excli
5. **AI сохраняет** — `excli scene export file.excalidraw`

#### Безопасность

Перед любыми большими изменениями:

```bash
excli snapshot save "before-refactoring"
```

Если что-то пошло не так:

```bash
excli snapshot restore "before-refactoring"
```

**Правило для AI-агента:** никогда не делай `excli clear --yes`, если человек мог вносить правки. Сначала `excli scene import`, потом работай.

---

## Продвинутое использование

### Переменная EXCALIDRAW_URL

По умолчанию excli подключается к `http://localhost:3000`. Можно изменить:

```bash
export EXCALIDRAW_URL=http://192.168.1.100:3000
excli health
```

Или для одной команды:

```bash
EXCALIDRAW_URL=http://remote:3000 excli list
```

### Режим --json

Все команды поддерживают `--json` для машиночитаемого вывода:

```bash
# Получить список элементов в JSON
excli --json list

# Получить описание канваса
excli --json describe

# Создать блок и получить его ID
excli --json box "Сервер" --at 100,200
```

Полезно для:
- Скриптов и пайплайнов
- AI-агентов, которые парсят вывод
- Интеграции с другими инструментами

### Фильтрация по типу

```bash
# Только прямоугольники
excli list -t rectangle

# Только стрелки
excli list -t arrow

# Только текст
excli list -t text
```

### Автоматический расчёт размеров

Если не указать `--size` при создании `box`, размер рассчитывается автоматически по тексту:
- Учитывается длина текста и количество строк
- Для `diamond` и `ellipse` размер увеличивается (текст должен вписаться)
- Кириллица поддерживается корректно

### Dry-run для YAML

Посмотреть layout без рендера:

```bash
excli render arch.excli.yaml --dry-run
```

Покажет позиции и размеры всех нод — полезно для отладки.

---

## Примеры

### Простой флоучарт

```bash
excli flow "Получил задачу -> Сделал -> Проверил -> Задеплоил" --palette warm
```

### Вертикальный флоу

```bash
excli flow "CEO -> CTO -> Team Lead -> Developer" -d vertical --palette mono
```

### Архитектура из YAML

Файл `arch.excli.yaml`:
```yaml
title: "Архитектура сервиса"
nodes:
  api:
    text: "API Gateway"
    style: blue
  auth:
    text: "Auth Service"
    style: red
    shape: diamond
  users:
    text: "Users DB"
    style: green
    size: large
  cache:
    text: "Redis"
    style: orange
    size: small
  queue:
    text: "RabbitMQ"
    style: purple
  worker:
    text: "Worker"
    style: cyan
edges:
  - [api, auth]
  - [auth, users]
  - [api, cache, {label: "cache hit"}]
  - [api, queue, {label: "async"}]
  - [queue, worker]
side:
  - {from: worker, to: email, text: "Уведомления", color: gray}
notes:
  - "API Gateway — единая точка входа"
  - "Auth использует JWT"
  - "Worker обрабатывает задачи из очереди"
```

```bash
excli render arch.excli.yaml --replace
```

### Несколько блоков вручную

```bash
excli clear --yes
excli box "Frontend" --at 100,100 --bg "#a5d8ff"
excli box "Backend" --at 400,100 --bg "#b2f2bb"
excli box "Database" --at 700,100 --bg "#ffec99"
# Получи ID из вывода, затем:
excli connect FRONTEND_ID BACKEND_ID --label "REST API"
excli connect BACKEND_ID DATABASE_ID --label "SQL"
```

---

## Установка canvas-сервера

excli — это CLI-клиент. Ему нужен canvas-сервер — [mcp_excalidraw](https://github.com/yctimlin/mcp_excalidraw).

### Docker (рекомендуется)

```bash
docker run -d -p 3000:3000 --name excalidraw-canvas ghcr.io/yctimlin/mcp_excalidraw-canvas:latest
```

Открой http://localhost:3000 — должен быть пустой канвас.

### Из исходников

```bash
git clone https://github.com/yctimlin/mcp_excalidraw.git
cd mcp_excalidraw
npm ci
npm run build
PORT=3000 npm run canvas
```

### Важные замечания

- **In-memory хранилище** — перезапуск сервера очищает канвас. Используй `excli scene export` и `excli snapshot save` для сохранения.
- **Localhost only** — сервер по умолчанию слушает только localhost. Для удалённого доступа используй `HOST=0.0.0.0`, но позаботься о безопасности.
- **Браузер нужен** — для экспорта в PNG и скриншотов канвас должен быть открыт в браузере.

---

## Лицензия

MIT — делай что хочешь.

Canvas-сервер [mcp_excalidraw](https://github.com/yctimlin/mcp_excalidraw) тоже MIT.
