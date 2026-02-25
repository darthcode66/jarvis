# Arquitetura Tecnica — Jarvis Bot

## Visao Geral

O Jarvis e um bot Telegram monolitico em Python que combina multiplas fontes de dados e camadas de processamento de linguagem natural para atuar como assistente pessoal.

## Camadas do Sistema

### 1. Camada de Transporte — Telegram
- **Biblioteca**: `python-telegram-bot` 20.7 (async)
- **Modo**: Long polling (`app.run_polling()`)
- **Parse mode**: HTML para mensagens com links (convertido de markdown pela IA)
- **Handlers registrados em**: `monitor.py` (entry point)

### 2. Camada de IA — Processamento de Linguagem Natural

#### Nivel 1: Groq API (primario)
- **Endpoint**: `https://api.groq.com/openai/v1/chat/completions`
- **Modelo primario**: `llama-3.3-70b-versatile`
- **Modelo fallback**: `llama-3.1-8b-instant`
- **Formato**: API compativel com OpenAI (messages com roles)
- **Timeout**: 15 segundos
- **Rate limiting**: Se recebe 429, tenta proximo modelo com 1s de delay

#### Nivel 2: Gemini API (fallback)
- **Endpoint**: `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`
- **Modelo primario**: `gemini-2.5-flash-lite`
- **Modelo fallback**: `gemini-2.5-flash`
- **Formato**: Formato Gemini nativo (contents com parts)
- **Conversao**: Historico unificado (user/assistant) e convertido para formato Gemini (user/model) antes do envio

#### Nivel 3: Jarvis NLP (fallback local)
- **Zero dependencias externas**
- **Pattern matching**: Palavras-chave normalizadas (sem acentos, lowercase)
- **Intencoes detectadas**: saudacao, agradecimento, onibus, aula, atividades, ajuda
- **Deteccao de rota**: Identifica origem e destino por posicao das palavras na frase

### 3. Camada de Dados

#### Horarios de Onibus (`onibus.py`)
- Dict Python hardcoded com 233 horarios
- Cada entrada: `{hora, linha, chegada, embarque, desembarque}`
- 5 rotas: casa_trabalho, trabalho_faculdade, faculdade_casa, casa_faculdade, trabalho_casa

#### Grade Academica (`aulas.py`)
- Dict Python com grade semanal
- Cada aula: `{materia, prof, inicio, fim}`

#### Atividades FAM (`fam_scraper.py` + `storage.py`)
- Scraping on-demand via Selenium (Chrome headless)
- Persistencia em JSON local
- Deteccao de novas atividades por comparacao de titulo + disciplina

## Fluxo Detalhado de uma Mensagem

```
1. Telegram envia update via long polling
2. python-telegram-bot roteia para o handler correto:
   a. Se e comando (/onibus, /aula, etc) → handler especifico
   b. Se e texto livre → mensagem_generica() em onibus.py

3. mensagem_generica():
   a. Chama gemini.perguntar(mensagem, chat_id)
      - Monta contexto dinamico (hora, local, proximos onibus, aulas)
      - Envia para Groq com system prompt + historico
      - Se Groq falha → tenta Gemini
      - Converte [markdown](links) para <a href>HTML</a>
   b. Se IA falha → chama jarvis.responder(update, context)
      - Normaliza texto, detecta intencao
      - Gera resposta local
   c. Se jarvis nao entendeu → mensagem generica "nao entendi"
```

## System Prompt da IA

O system prompt inclui:
1. **Personalidade**: Jarvis — formal, humor acido, sarcasmo sutil
2. **Dados do Pedro**: Locais, horarios, curso
3. **Regras de onibus**: Nunca inventar horarios, usar so dados fornecidos
4. **Formatacao**: Template obrigatorio com emojis e links Maps
5. **Grade semanal**: Todas as materias e professores
6. **Tabela completa de horarios**: Todas as 233 entradas, gerada automaticamente pelo `_gerar_tabela_horarios()`

## Contexto Dinamico

Gerado a cada mensagem por `_contexto_dinamico()`:
- Data/hora atual (timezone SP)
- Local estimado do Pedro (baseado em dia/hora)
- Aulas de hoje e amanha
- Proximos 5 onibus de cada rota relevante ao local atual
- Links do Google Maps para cada ponto de embarque

## Estimativa de Local

```python
# _local_estimado() em gemini.py
Fim de semana → casa
Antes das 8h → casa
8h - 17:30 → trabalho
17:30 - 19h (sem aula) → trabalho/casa
17:30 - 19h (com aula) → trabalho
19h - 23h (com aula) → faculdade
Apos 23h → casa
```

## Historico de Conversa

- Armazenado em memoria: `dict[chat_id, list[dict]]`
- Formato unificado: `{"role": "user"|"assistant", "content": str}`
- Maximo 20 mensagens por chat
- Compartilhado entre Groq e Gemini (com conversao de formato)
- Limpo com comando `/clear`
- Nao persiste entre reinicializacoes do bot

## Formatacao de Saida

A IA gera markdown, que passa por `_formatar_para_telegram()`:
- Regex encontra `[texto](url)`
- Converte para `<a href="url">texto</a>`
- Escapa HTML no resto do texto via `html.escape()`
- Resultado enviado com `parse_mode="HTML"`
