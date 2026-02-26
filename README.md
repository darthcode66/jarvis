# Famus - Assistente Pessoal no Telegram

Bot Telegram que funciona como assistente pessoal inteligente, combinando IA conversacional (Groq/Gemini), horarios de onibus em tempo real, grade academica e consulta de atividades do portal FAM.

Desenvolvido por **Pedro** com auxilio do **Claude Code** (Anthropic).

---

## Funcionalidades

### Assistente IA (Famus)
- Personalidade paulista: humor acido, sarcasmo sutil, girias naturais (mano, firmeza, suave, da hora)
- Memoria de conversa (historico por chat, ate 20 mensagens)
- Contexto dinamico: sabe a hora, dia, local estimado do usuario e proximos onibus
- **Groq (Llama 3.3 70B)** como IA primaria — respostas em sub-segundo
- **Gemini Flash** como fallback automatico
- **Pattern matching local** como fallback final (sem API, sem custo)

### Horarios de Onibus
- **5 rotas** entre Casa, Trabalho e Faculdade
- **233 horarios** mapeados (dia util completo)
- **8 linhas** de onibus (102, 103, 105, 114, 118, 200, 205, 213, 220, 225)
- Filtra automaticamente os proximos onibus pela hora atual
- Links do Google Maps para rota a pe ate o ponto de embarque
- Botoes inline para navegacao rapida entre rotas

### Grade Academica
- Grade completa do 5o semestre de Ciencia da Computacao (noturno) - FAM
- Consulta por dia, amanha ou semana inteira
- Detecta dia da semana automaticamente

### Portal FAM
- Scraping automatizado do portal academico via Selenium
- Extracao de atividades, prazos, materiais e descricoes
- Deteccao de novas atividades

---

## Arquitetura

```
jarvis/
├── src/
│   ├── monitor.py          # Entry point — registra handlers e inicia polling
│   ├── gemini.py           # Integracao IA (Groq + Gemini) + system prompt
│   ├── famus.py            # NLP local por pattern matching (fallback)
│   ├── onibus.py           # Dados de horarios + handlers Telegram
│   ├── aulas.py            # Grade horaria + handlers Telegram
│   ├── fam_scraper.py      # Scraper Selenium do portal FAM
│   ├── storage.py          # Persistencia JSON de atividades
│   └── telegram_bot.py     # Classe TelegramNotifier (notificacoes)
├── data/
│   └── atividades.json     # Historico de atividades (gerado automaticamente)
├── logs/
│   └── monitor.log         # Log da aplicacao
├── docs/
│   ├── ARQUITETURA.md      # Documentacao tecnica detalhada
│   ├── ROTAS.md            # Metodologia de calculo dos horarios
│   └── API.md              # APIs externas utilizadas
├── .env                    # Variaveis de ambiente (NAO versionar)
├── .env.example            # Template das variaveis
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Fluxo de Mensagens

```
Mensagem do usuario
        │
        ▼
  ┌─────────────┐
  │  Comando?   │──── Sim ──→ Handler especifico (/onibus, /aula, /atividades)
  │  (/start...)│
  └─────────────┘
        │ Nao
        ▼
  ┌─────────────┐
  │  Groq API   │──── Sucesso ──→ Resposta formatada (HTML)
  │  (Llama 3.3)│
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
  "Nao entendi, use /help"
```

---

## Modulos

### `monitor.py` — Entry Point
- Carrega `.env` e configura logging
- Registra handlers de todos os modulos (onibus, aulas, atividades)
- Inicia o bot em modo polling
- Gerencia scraping do portal FAM via Selenium (blocking → `run_in_executor`)

### `gemini.py` — Integracao IA
- **Groq API** (primario): Llama 3.3 70B via API compativel com OpenAI
- **Gemini API** (fallback): Flash Lite e Flash
- System prompt com personalidade Famus, dados do usuario, grade e tabela completa de horarios
- Contexto dinamico gerado a cada mensagem: hora, local estimado, proximos onibus, aulas do dia
- Historico de conversa por chat_id (unificado entre providers)
- Conversao de markdown `[text](url)` para HTML `<a>` tags para o Telegram

### `famus.py` — NLP Local
- Pattern matching por palavras-chave (sem API)
- Detecta intencoes: saudacao, agradecimento, onibus (com rota), aulas, atividades, ajuda
- Normalizacao de texto (remove acentos, lowercase)
- Deteccao inteligente de origem/destino para rotas de onibus
- Fallback quando ambas as APIs falham

### `onibus.py` — Horarios de Onibus
- Dict `HORARIOS` com 5 rotas e 233 horarios completos
- Funcoes: `proximos_onibus()`, `todos_horarios()`, `resumo_trajetos()`
- Handlers Telegram: comandos, callbacks inline, menu de botoes
- Handler generico `mensagem_generica()`: tenta IA primeiro, famus.py como fallback

### `aulas.py` — Grade Horaria
- Grade do 5o semestre CC noturno (Turma 57-05-B)
- Formatacao por dia, amanha ou semana
- Handlers com botoes inline para navegacao

### `fam_scraper.py` — Scraper do Portal
- Login automatizado no portal FAM
- Navegacao ate pagina de atividades
- Extracao de titulo, disciplina, professor, prazo, situacao, descricao e materiais
- Usa Selenium + BeautifulSoup para parsing

### `storage.py` — Persistencia
- Armazena historico de atividades em JSON
- Detecta novas atividades comparando com historico
- Estatisticas de uso

### `telegram_bot.py` — Notificador
- Classe `TelegramNotifier` para envio de mensagens formatadas
- Retry automatico em caso de timeout
- Formatacao Markdown com escape de caracteres especiais

---

## Rotas de Onibus

| Rota | Linhas | Horarios | Embarque principal |
|------|--------|----------|--------------------|
| Casa → Trabalho | L.220, L.213 | 47 | R. Cira de O. Petrin / R. Rio das Velhas |
| Trabalho → Faculdade | L.102, L.103, L.105, L.114, L.118, L.200, L.205, L.225 | 64 | Av. de Cillo, 269 |
| Faculdade → Casa | L.220, L.213 | 47 | R. Sao Gabriel / R. Paraná |
| Casa → Faculdade | L.220 | 28 | R. Cira de O. Petrin, 622 |
| Trabalho → Casa | L.220, L.213 | 47 | R. Rui Barbosa, 261 / R. Brasil |

**Total: 233 horarios de dia util**

### Fonte dos dados
- API **Mobilibus** (`mobilibus.com/api/`) — mesma API usada pelo app Bus2You da SOU Transportes
- Calculo de horario nos pontos via offset temporal (campo `int` = segundos acumulados por parada)
- Distancias calculadas com formula de **Haversine** entre coordenadas GPS
- Verificacao de sentido/direcao dos trips para garantir origem → destino correto

---

## Setup

### Pre-requisitos
- Python 3.11+
- Google Chrome + ChromeDriver (para scraping do portal FAM)
- Conta no Telegram + bot criado via @BotFather

### Instalacao

```bash
git clone git@github.com:darthcode66/jarvis.git
cd jarvis

# Criar e ativar virtualenv
python3 -m venv venv
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Configurar variaveis de ambiente
cp .env.example .env
# Editar .env com suas credenciais
```

### Obtendo as chaves de API

1. **Telegram Bot Token**: Fale com @BotFather no Telegram → `/newbot`
2. **Telegram Chat ID**: Envie uma mensagem pro bot, depois acesse `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. **Groq API Key**: Cadastre em [console.groq.com](https://console.groq.com) (gratuito)
4. **Gemini API Key**: Cadastre em [aistudio.google.com](https://aistudio.google.com/apikey) (gratuito)
5. **FAM Login/Senha**: Credenciais do portal academico da FAM

### Executando localmente

```bash
cd src
python monitor.py
```

### Executando em background (local)

```bash
nohup python src/monitor.py > /dev/null 2>&1 &
```

---

## Deploy em Producao (AWS EC2)

O bot roda 24/7 em uma instancia **AWS EC2 t2.micro** (free tier, 12 meses).

### Infraestrutura

| Recurso | Especificacao |
|---------|---------------|
| Instancia | EC2 t2.micro (1 vCPU, 1GB RAM) |
| SO | Ubuntu 24.04 LTS |
| Regiao | us-east-1 (N. Virginia) |
| Acesso | SSH via key pair |
| Servico | systemd (reinicio automatico) |
| Custo | $0 (free tier) |

### Protecoes contra custos

- **Budget Alert $0.01**: Email se qualquer centavo for cobrado
- **Budget Alert $0.80 + previsao**: Email se gasto chegar perto de $1
- **Politica IAM**: Bloqueia criacao de RDS, Load Balancer, NAT Gateway e Elastic IP

### Conectar via SSH

```bash
ssh -i ~/.ssh/jarvis-aws.pem ubuntu@<IP_PUBLICO>
```

### Gerenciar o servico

```bash
sudo systemctl status famus    # Ver status
sudo systemctl restart famus   # Reiniciar
sudo systemctl stop famus      # Parar
sudo journalctl -u famus -f    # Ver logs em tempo real
```

### Atualizar o bot no servidor

```bash
scp -i ~/.ssh/jarvis-aws.pem src/*.py ubuntu@<IP_PUBLICO>:~/jarvis/src/
ssh -i ~/.ssh/jarvis-aws.pem ubuntu@<IP_PUBLICO> "sudo systemctl restart famus"
```

---

## Comandos do Bot

| Comando | Descricao |
|---------|-----------|
| `/start` | Menu principal com botoes |
| `/onibus` | Proximos onibus de todas as rotas |
| `/aula` | Aulas de hoje |
| `/atividades` | Consulta atividades do portal FAM |
| `/help` | Lista de comandos |
| `/clear` | Limpa historico de conversa da IA |

### Linguagem Natural
O bot tambem entende mensagens em linguagem natural:
- "que aula tem hoje?" → mostra grade do dia
- "onibus pro trabalho" → proximos onibus Casa → Trabalho
- "quero ir pra faculdade" → proximos onibus para a FAM
- "melhor rota do trabalho pra casa" → proximos onibus Trabalho → Casa

---

## Stack Tecnica

| Componente | Tecnologia |
|------------|------------|
| Linguagem | Python 3.11+ |
| Bot Telegram | python-telegram-bot 20.7 |
| IA Primaria | Groq API (Llama 3.3 70B Versatile) |
| IA Fallback | Google Gemini API (Flash Lite / Flash) |
| NLP Local | Pattern matching customizado |
| Web Scraping | Selenium + BeautifulSoup |
| Dados de Onibus | API Mobilibus (SOU Transportes Americana) |
| Timezone | America/Sao_Paulo (ZoneInfo) |
| Persistencia | JSON local |
| Infraestrutura | AWS EC2 t2.micro (free tier) |
| CI/CD | Deploy manual via SCP + systemd |

---

## Historico do Projeto

1. **v1.0** — Bot basico com scraping do portal FAM e notificacoes de atividades
2. **v2.0** — Adicionados horarios de onibus (rota trabalho→faculdade, 23 horarios)
3. **v3.0** — Grade academica, NLP local (famus.py), botoes inline
4. **v4.0** — Integracao Gemini AI com personalidade Famus
5. **v5.0** — Migracao para Groq (Llama 3.3 70B) + Gemini como fallback
6. **v6.0** — Dados completos de todas as 5 rotas (233 horarios), formatacao aprimorada, reorganizacao do projeto
7. **v7.0** — Deploy em producao na AWS EC2, caminhos relativos, servico systemd 24/7
8. **v8.0** — Rebrand Jarvis → Famus, personalidade paulista para universitarios da FAM

---

## Licenca

Projeto pessoal de uso academico. Desenvolvido por Pedro com Claude Code (Anthropic).
