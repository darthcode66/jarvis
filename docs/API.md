# APIs Externas Utilizadas

## 1. Telegram Bot API

- **Biblioteca**: `python-telegram-bot` 20.7
- **Documentacao**: https://docs.python-telegram-bot.org/
- **Autenticacao**: Token do @BotFather via env `TELEGRAM_BOT_TOKEN`
- **Modo**: Long polling (nao webhook)
- **Recursos usados**: Mensagens, inline keyboards, callback queries, comandos

## 2. Groq API (IA Primaria)

- **Endpoint**: `https://api.groq.com/openai/v1/chat/completions`
- **Documentacao**: https://console.groq.com/docs
- **Autenticacao**: Bearer token via env `GROQ_API_KEY`
- **Modelos**: `llama-3.3-70b-versatile` (primario), `llama-3.1-8b-instant` (fallback)
- **Formato**: Compativel com OpenAI (messages array com system/user/assistant)
- **Custo**: Gratuito (free tier generoso)
- **Limites**: ~30 req/min no free tier
- **Timeout**: 15s
- **Parametros usados**:
  ```json
  {
    "model": "llama-3.3-70b-versatile",
    "messages": [...],
    "temperature": 0.7,
    "max_tokens": 2048
  }
  ```

## 3. Google Gemini API (IA Fallback)

- **Endpoint**: `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={API_KEY}`
- **Documentacao**: https://ai.google.dev/docs
- **Autenticacao**: API key como query parameter via env `GEMINI_API_KEY`
- **Modelos**: `gemini-2.5-flash-lite` (primario), `gemini-2.5-flash` (fallback)
- **Formato**: Formato Gemini nativo (contents com parts)
- **Custo**: Gratuito (free tier)
- **Limites**: ~20 req/min no free tier (429 frequente sob carga)
- **Timeout**: 15s
- **Parametros usados**:
  ```json
  {
    "system_instruction": {"parts": [{"text": "..."}]},
    "contents": [{"role": "user|model", "parts": [{"text": "..."}]}],
    "generationConfig": {
      "temperature": 0.7,
      "maxOutputTokens": 2048
    }
  }
  ```

## 4. API Mobilibus (Dados de Onibus)

- **Base URL**: `https://mobilibus.com/api/`
- **Documentacao**: Nao-oficial (engenharia reversa do app Bus2You)
- **Autenticacao**: Nenhuma (API publica)
- **Project ID**: 481 (Americana, SP)
- **Nota**: API usada apenas durante o desenvolvimento para extrair dados. Os horarios sao hardcoded no bot — nao ha chamadas em runtime.

### Endpoints relevantes:

| Endpoint | Descricao |
|----------|-----------|
| `GET /api/project-details?project_hash=4l1q9` | Dados do projeto |
| `GET /api/routes?origin=web&project_id=481` | Lista de linhas |
| `GET /api/timetable?origin=web&v=2&project_id=481&route_id={id}` | Horarios de uma linha |
| `GET /api/trip-details?origin=web&v=2&trip_id={id}` | Paradas com coordenadas |

## 5. Portal FAM (Web Scraping)

- **URL**: `https://www.famportal.com.br/`
- **Metodo**: Selenium + Chrome headless
- **Autenticacao**: Login/senha do aluno via env `FAM_LOGIN` / `FAM_SENHA`
- **Recursos extraidos**: Lista de atividades, detalhes, materiais, prazos
- **Nota**: Scraping on-demand (apenas quando usuario usa /atividades)

## 6. Google Maps (Links)

- **Endpoint**: `https://www.google.com/maps/dir/`
- **Uso**: Apenas geracao de links (sem API call)
- **Parametros**: `destination={endereco}&travelmode=walking`
- **Custo**: Nenhum (apenas links para o Maps web)
