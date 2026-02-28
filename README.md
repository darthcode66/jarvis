# FAMus Bot v1.0.0

Assistente pessoal no Telegram para alunos da FAM (Faculdade de Americana).

Grade de aulas, boletim, horarios de onibus SOU Americana, simulacao de notas, notificacoes automaticas de notas/faltas e IA integrada — tudo no Telegram.

Desenvolvido por **Pedro Henrique Alves Marcandali** com auxilio do **Claude Code** (Anthropic).

---

## Funcionalidades

### Assistente IA
- Personalidade paulista: girias naturais (mano, suave, trampo), humor sutil
- Contexto dinamico: hora, local estimado, aulas do dia, notas, faltas, proximos onibus
- **Groq (Llama 3.3 70B)** como IA primaria — respostas em sub-segundo
- **Gemini Flash Lite** como fallback automatico
- **Pattern matching local** como fallback final (sem API, sem custo)
- Historico de conversa por chat (ate 20 mensagens, em memoria)
- Limite Free: 5 mensagens IA/dia | Pro: ilimitado

### Portal Academico
- Scraping automatizado do portal FAM via Selenium + Chrome headless
- Importacao de grade horaria, notas, faltas, info do aluno e historico
- Notificacoes automaticas de mudancas em notas e faltas (Pro, a cada 2h)

### Horarios de Onibus (Pro)
- **5 rotas** entre Casa, Trabalho e Faculdade
- **233 horarios** mapeados (dia util completo)
- **10 linhas** de onibus SOU Americana
- Filtra automaticamente proximos onibus pela hora atual
- Links do Google Maps para rota a pe ate o ponto de embarque
- Botoes inline para navegacao entre rotas

### Grade de Aulas
- Grade dinamica por usuario (importada do portal)
- Consulta por hoje, amanha ou semana inteira
- Botoes inline para navegacao

### Simulacao de Notas (Pro)
- Calcula quanto o aluno precisa tirar pra passar
- Formula FAM: MS = media ponderada N1/N2/N3, aprovacao >= 6.0
- Considera AR (avaliacao de recuperacao) quando MS < 6.0

---

## Planos e Monetizacao

| Recurso | Free | Pro (R$ 9,90/mês) |
|---------|------|-----|
| `/aula` — grade de aulas | Livre | Livre |
| `/notas` — boletim | 1x/semana | Ilimitado |
| `/onibus` — horarios de onibus | Bloqueado | Livre |
| `/faltas` — faltas por disciplina | Bloqueado | Livre |
| `/simular` — simulacao de notas | Bloqueado | Livre |
| `/dp` — materias reprovadas | Bloqueado | Livre |
| `/atividades` — atividades do portal | Bloqueado | Livre |
| IA conversacional | 5 msgs/dia | Ilimitada |
| Notificacoes automaticas | Nao | Sim (a cada 2h) |

- **Trial**: 7 dias gratis de Pro no cadastro
- **Pagamento**: Mercado Pago (PIX avulso ou assinatura mensal com cartao)
- **Expiração**: job automatico faz downgrade quando plano expira

---

## Comandos do Bot

| Comando | Descricao | Acesso |
|---------|-----------|--------|
| `/start` | Menu principal | Todos |
| `/aula` | Grade de aulas (hoje, amanha, semana) | Todos |
| `/notas` | Boletim do portal FAM | Free 1x/semana |
| `/grade` | Re-importar grade do portal | Todos |
| `/onibus` | Horarios de onibus SOU | Pro |
| `/faltas` | Faltas por disciplina | Pro |
| `/simular` | Simulacao — quanto preciso pra passar | Pro |
| `/dp` | Materias reprovadas (dependencias) | Pro |
| `/atividades` | Atividades do portal FAM | Pro |
| `/assinar` | Assinar plano Pro | Todos |
| `/plano` | Ver/gerenciar seu plano | Todos |
| `/config` | Ver dados cadastrados | Todos |
| `/resetar` | Resetar cadastro (preserva plano) | Todos |
| `/help` | Lista de comandos | Todos |
| `/clear` | Limpar historico da IA | Todos |
| `/suporte` | Enviar mensagem de suporte | Todos |
| `/sugestao` | Enviar sugestao | Todos |

### Linguagem Natural
O bot tambem entende mensagens de texto livre:
- "que aula tem hoje?" → mostra grade do dia
- "como estao minhas notas?" → mostra informacoes academicas
- "onibus pro trabalho" → horarios de onibus (Pro)
- "quanto preciso pra passar em fisica?" → simulacao (Pro, redireciona para /assinar)

---

## Arquitetura

```
jarvis/
├── src/
│   ├── monitor.py          # Entry point — handlers, polling, jobs, comandos
│   ├── cadastro.py          # Onboarding — ConversationHandler completo
│   ├── gemini.py            # IA (Groq + Gemini) + system prompt dinamico
│   ├── famus.py             # NLP local por pattern matching (fallback)
│   ├── onibus.py            # Horarios de onibus + handlers + /help
│   ├── aulas.py             # Grade horaria + handlers
│   ├── db.py                # SQLite — usuarios, notas, grade, pagamentos
│   ├── fam_scraper.py       # Selenium — scraping do portal FAM
│   ├── pagamento.py         # Mercado Pago — PIX, assinaturas
│   ├── crypto.py            # Fernet — encriptacao de credenciais
│   ├── storage.py           # Persistencia JSON (legado)
│   └── telegram_bot.py      # TelegramNotifier (legado)
├── tests/
│   └── test_validacoes.py   # Suite de testes (169 testes)
├── data/
│   ├── famus.db             # Banco SQLite
│   └── backups/             # Backups rotativos (cron 6h)
├── logs/
│   └── notas_debug.html     # Debug HTML do ultimo scrape
├── docs/
│   ├── ARQUITETURA.md       # Documentacao tecnica
│   ├── ROTAS.md             # Metodologia dos horarios
│   ├── API.md               # APIs externas
│   └── pesquisa-mercado.md  # Analise de mercado e precificacao
├── .env                     # Variaveis de ambiente (NAO versionar)
├── requirements.txt
└── README.md
```

---

## Modulos

### `monitor.py` — Entry Point
- Carrega `.env`, configura logging, inicializa banco
- Registra handlers de todos os modulos
- Inicia bot em modo polling
- Jobs automaticos:
  - `job_verificar_atualizacoes` — scrape notas/faltas a cada 2h (so Pro)
  - `verificar_assinaturas` — checa pagamentos pendentes a cada 5min
  - `job_expirar_planos` — downgrade de planos expirados
- Comandos: `/notas`, `/faltas`, `/simular`, `/dp`, `/atividades`, `/assinar`, `/plano`

### `cadastro.py` — Onboarding
- ConversationHandler com 11 estados:
  ```
  NOME → CASA → TRABALHO → HORARIO_ENTRADA → HORARIO_SAIDA → TRANSPORTE → TURNO → FAM_LOGIN → FAM_SENHA → TERMOS → CONFIRMA
  ```
- Validacoes:
  - CPF: 11 digitos (aceita formatado: 123.456.789-00)
  - Endereco: geocodificacao via Nominatim/OpenStreetMap (fallback graceful)
  - Horario: formato HH:MM
- Tipo de transporte: SOU Americana, EMTU, Carro/Carona, Outro
- Termos de uso (LGPD compliance) com aceite explicito
- Scrape automatico no final: grade + notas + info + historico
- Trial de 7 dias ativado automaticamente
- `/config` — mostra dados cadastrados
- `/resetar` — confirmacao com botoes, preserva plano/pagamentos

### `gemini.py` — Integracao IA
- **Groq** (primario): Llama 3.3 70B + 8B fallback
- **Gemini** (fallback): Flash Lite + Flash
- System prompt personalizado por usuario:
  - Dados pessoais, locais, transporte
  - Grade semanal completa
  - Regras de onibus (so Pro + SOU)
  - Regras de simulacao (so Pro)
- Contexto dinamico a cada mensagem:
  - Hora, dia, local estimado
  - Aulas hoje/amanha
  - Dados academicos (curso, semestre, sala)
  - Notas, faltas, simulacao (Pro)
  - DPs/historico
  - Proximos onibus relevantes (Pro + SOU)
- Respeita gates: free nao recebe dados de simulacao nem onibus

### `db.py` — Banco de Dados
- SQLite em `data/famus.db`
- Tabelas: `usuarios`, `eventos`, `pagamentos`, `leads`, `suporte`, `sugestoes`
- Credenciais FAM encriptadas com Fernet
- Migracoes automaticas via ALTER TABLE em `init_db()`
- Funcoes principais:
  - CRUD de usuarios (`create_user`, `update_user`, `get_user`)
  - Grade/notas/historico como JSON (`set_grade`, `get_notas`, etc.)
  - Plano (`set_plano`, `get_plano`, `is_pro`, `ativar_trial`)
  - Analytics (`log_evento`, `ultimo_evento`)
  - Pagamentos (`criar_pagamento`, `atualizar_pagamento`)

### `fam_scraper.py` — Scraper do Portal
- Selenium + Chrome headless
- `fazer_login()` — login automatizado
- `extrair_grade()` → grade horaria (parser HTML)
- `extrair_notas()` → `(notas_list, info_aluno_dict)`
- `extrair_atividades()` → lista de atividades/tarefas
- `extrair_historico()` → historico academico completo
- Debug HTML salvo em `logs/notas_debug.html`

### `onibus.py` — Horarios de Onibus
- 5 rotas com 233 horarios de dia util
- Funcoes: `proximos_onibus()`, `todos_horarios()`, `resumo_trajetos()`
- Handlers: `/onibus`, `/casa_trabalho`, `/casa_faculdade`, etc.
- Callbacks inline para navegacao
- Checagem de transporte (so exibe para usuarios SOU)
- Handler generico `mensagem_generica()`: IA → famus.py → fallback

### `pagamento.py` — Mercado Pago
- PIX avulso (Checkout Pro)
- Assinatura mensal recorrente
- Polling de status de pagamento
- Cancelamento de assinatura

---

## Fluxo de Onboarding

```
/start
  │
  ├─ Ja cadastrado? → Menu principal
  │
  └─ Novo usuario:
       │
       ├─ 1. Nome
       ├─ 2. Endereco de casa (validacao Nominatim)
       ├─ 3. Endereco do trabalho (ou "pular")
       ├─ 4. Horario entrada trabalho (HH:MM)
       ├─ 5. Horario saida trabalho (HH:MM)
       ├─ 6. Transporte [SOU | EMTU | Carro | Outro]
       ├─ 7. Turno [Matutino | Vespertino | Noturno]
       ├─ 8. Login FAM (CPF, validacao 11 digitos)
       ├─ 9. Senha FAM (msg apagada apos leitura)
       ├─ 10. Termos de uso (aceite obrigatorio)
       ├─ 11. Resumo + confirmacao
       │
       └─ Scrape automatico: grade + notas + info + historico
          Trial de 7 dias ativado
```

---

## Fluxo de Mensagens

```
Mensagem do usuario
        │
        ▼
  ┌─────────────┐
  │  Comando?   │──── Sim ──→ Handler especifico
  │  (/start...)│           (com gate Pro quando aplicavel)
  └─────────────┘
        │ Nao
        ▼
  ┌─────────────┐
  │ Limite IA?  │──── Free: 5/dia atingido ──→ Msg paywall
  └─────────────┘
        │ Ok
        ▼
  ┌─────────────┐
  │  Groq API   │──── Sucesso ──→ Resposta formatada (HTML)
  │ (Llama 3.3) │
  └─────────────┘
        │ Falha
        ▼
  ┌─────────────┐
  │ Gemini API  │──── Sucesso ──→ Resposta formatada (HTML)
  │  (fallback) │
  └─────────────┘
        │ Falha
        ▼
  ┌─────────────┐
  │  Famus NLP  │──── Detectou ──→ Resposta local (sem API)
  │  (patterns) │
  └─────────────┘
        │ Nao detectou
        ▼
  "Estou com dificuldade, tente /help"
```

---

## Estruturas de Dados

### notas (JSON, lista)
```json
[{
  "disciplina": "Fisica Geral e Experimental",
  "n1": 7.5,
  "n2": null,
  "n3": null,
  "media_semestral": null,
  "media_final": null,
  "faltas": 2,
  "max_faltas": 20
}]
```

### info_aluno (JSON, dict)
```json
{
  "curso": "Ciencia da Computacao",
  "semestre": "5",
  "sala": "Bloco 2 - Sala 073 - 1o piso",
  "turma_codigo": "57-05-B"
}
```

### grade (JSON, dict por dia da semana)
```json
{
  "0": [{"materia": "Prog. Orientada a Objetos", "prof": "Evandro", "inicio": "19:00", "fim": "22:30"}],
  "1": [],
  "2": [{"materia": "Fisica", "prof": "Henrique", "inicio": "19:00", "fim": "22:30"}]
}
```

---

## Rotas de Onibus

| Rota | Linhas | Horarios | Embarque principal |
|------|--------|----------|--------------------|
| Casa → Trabalho | L.220, L.213 | 47 | R. Cira de O. Petrin / R. Rio das Velhas |
| Trabalho → Faculdade | L.102, L.103, L.105, L.114, L.118, L.200, L.205, L.225 | 64 | Av. de Cillo, 269 |
| Faculdade → Casa | L.220, L.213 | 47 | R. Sao Gabriel / R. Parana |
| Casa → Faculdade | L.220 | 28 | R. Cira de O. Petrin, 622 |
| Trabalho → Casa | L.220, L.213 | 47 | R. Rui Barbosa, 261 / R. Brasil |

**Total: 233 horarios de dia util**

Fonte: API Mobilibus (mesma do app Bus2You da SOU Transportes)

---

## Stack Tecnica

| Componente | Tecnologia |
|------------|------------|
| Linguagem | Python 3.11+ |
| Bot Telegram | python-telegram-bot 20.7 |
| IA Primaria | Groq API (Llama 3.3 70B Versatile) |
| IA Fallback | Google Gemini API (Flash Lite / Flash) |
| NLP Local | Pattern matching customizado |
| Banco de Dados | SQLite |
| Encriptacao | Fernet (cryptography) |
| Web Scraping | Selenium + BeautifulSoup + Chrome headless |
| Dados de Onibus | API Mobilibus (SOU Transportes Americana) |
| Pagamento | Mercado Pago (PIX + assinatura) |
| Geocodificacao | Nominatim / OpenStreetMap |
| Timezone | America/Sao_Paulo (ZoneInfo) |
| Infraestrutura | AWS EC2 t2.micro |
| Deploy | SCP + systemd |
| Backup | Cron rotativo a cada 6h (7 copias) |

---

## Setup

### Pre-requisitos
- Python 3.11+
- Google Chrome + ChromeDriver (para scraping)
- Conta no Telegram + bot via @BotFather

### Variaveis de ambiente (.env)
```env
TELEGRAM_BOT_TOKEN=...
GROQ_API_KEY=...
GEMINI_API_KEY=...
FERNET_KEY=...
MERCADOPAGO_ACCESS_TOKEN=...
```

### Instalacao

```bash
git clone git@github.com:darthcode66/jarvis.git
cd jarvis
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Editar .env com suas credenciais
```

### Executando

```bash
cd src
python monitor.py
```

---

## Deploy (AWS EC2)

| Recurso | Especificacao |
|---------|---------------|
| Instancia | EC2 t2.micro (1 vCPU, 1GB RAM) |
| SO | Ubuntu 24.04 LTS |
| Regiao | us-east-1 |
| Servico | systemd (`famus.service`) |
| Backup | Cron a cada 6h, 7 copias rotativas |

### Comandos uteis

```bash
# SSH
ssh -i ~/.ssh/jarvis-aws.pem ubuntu@<IP>

# Status
sudo systemctl status famus

# Restart
sudo systemctl restart famus

# Logs
sudo journalctl -u famus -f

# Deploy
scp -i ~/.ssh/jarvis-aws.pem src/*.py ubuntu@<IP>:~/jarvis/src/
ssh -i ~/.ssh/jarvis-aws.pem ubuntu@<IP> "sudo systemctl restart famus"
```

---

## Testes

```bash
# Todos os testes (exceto Nominatim)
python -m pytest tests/ -v --skip-nominatim

# Incluindo Nominatim (requer internet, ~10s)
python -m pytest tests/ -v

# Testes especificos
python -m pytest tests/test_validacoes.py -k "cpf" -v
```

Suite com 169 testes cobrindo:
- Validacoes (CPF, horario, transporte, endereco)
- Handlers com mocks (todos os estados do onboarding)
- Integracao (onibus + transporte, gemini + transporte)
- Fluxos completos de onboarding
- Migracao do banco

---

## Historico de Versoes

| Versao | Descricao |
|--------|-----------|
| v0.1 | Bot basico com scraping de atividades do portal FAM |
| v0.2 | Horarios de onibus (rota trabalho→faculdade, 23 horarios) |
| v0.3 | Grade academica, NLP local (famus.py), botoes inline |
| v0.4 | Integracao Gemini AI com personalidade Famus |
| v0.5 | Migracao para Groq (Llama 3.3 70B) + Gemini fallback |
| v0.6 | 5 rotas completas (233 horarios), reorganizacao |
| v0.7 | Deploy AWS EC2, servico systemd 24/7 |
| v0.8 | Rebrand Jarvis → FAMus |
| v0.9 | Onboarding multi-usuario, banco SQLite, credenciais encriptadas |
| **v1.0.0** | **Lancamento: monetizacao (Mercado Pago), gates Pro/Free, validacoes (CPF, Nominatim, transporte), notificacoes automaticas, trial 7 dias, testes, backup** |

---

## Licenca

Projeto academico. Desenvolvido por Pedro Henrique Alves Marcandali com Claude Code (Anthropic).
