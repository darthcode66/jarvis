# FAMus Bot — Pesquisa de Mercado e Precificação

*Data: 26/02/2026*

---

## 1. O que é o FAMus Bot

Bot Telegram para universitários brasileiros que integra com o portal acadêmico da faculdade. Oferece:

- Notificações automáticas de notas e faltas (a cada 2h)
- Consulta de grade horária
- Consulta de atividades/tarefas pendentes
- Horários de ônibus para a faculdade
- Assistente IA integrado (Llama 3.3 70B + Gemini fallback) com contexto acadêmico personalizado
- Scraping automático do portal FAM

---

## 2. Competidores

### 2.1 Bots Institucionais (gratuitos, feitos pela IES)

| Serviço | Plataforma | O que faz | Limitações |
|---|---|---|---|
| UNIBot (Unicesumar) | WhatsApp | Notas, boletos, horários | SAC glorificado, sem proatividade |
| AVA Bot (Anhanguera/Kroton) | WhatsApp + App | Notas, faltas, financeiro | Interface ruim, sem IA |
| Bia (Estácio) | WhatsApp | Consulta geral | Atendimento genérico |
| Chatbot Mackenzie | WhatsApp/Site | Consulta acadêmica | Sem notificações push |

**Padrão:** Todos são focados em atendimento (substituir SAC), não em produtividade do aluno. Nenhum faz notificação proativa, nenhum tem IA contextual.

### 2.2 Projetos Indie (não comerciais)

| Projeto | Plataforma | Status |
|---|---|---|
| SIGAA Bots (vários no GitHub) | Telegram | Projetos individuais de alunos, descontinuados |
| Bot Notas UTFPR | Telegram | Descontinuado |
| Moodle Telegram Bots | Telegram | Projetos pequenos |

**Nenhum é comercial.** São projetos de alunos para uso pessoal — exatamente como o FAMus começou.

### 2.3 Apps de Estudo (B2C)

| App | Preço | Foco | Integra com portal? |
|---|---|---|---|
| Passei Direto | Grátis / R$19,90/mês | Materiais e resumos | Não |
| Me Salva! | R$34,90 a R$59,90/mês | Videoaulas | Não |
| Descomplica | R$39,90 a R$89,90/mês | Videoaulas, graduação | Não |
| Gabaritou | Grátis / ~R$9,90/mês | Organização de estudos | Não |
| Studos | Grátis / ~R$14,90/mês | Planner, pomodoro | Não |

**Nenhum integra com o portal acadêmico.** São plataformas de conteúdo, não de gestão acadêmica pessoal.

### 2.4 Referências Internacionais

| Serviço | País | Modelo | Relevância |
|---|---|---|---|
| **UniNow** | Alemanha | Agregou portais de 100+ universidades. Foi adquirida. | Modelo mais próximo do FAMus |
| **Studo** | Áustria | Híbrido B2B/B2C, ~30 universidades | Inclui cantina, transporte, email |
| Coursicle | EUA | Grátis / Pro US$4,99 (único) | Rastreamento de vagas em disciplinas |
| iStudiez Pro | Ucrânia | US$2,99 a US$9,99 | Horários, notas, GPA tracker |
| MyStudyLife | UK | Grátis (ads) | Grade, tarefas, lembretes |

---

## 3. Análise de Mercado

### 3.1 Números

| Métrica | Valor |
|---|---|
| Universitários no Brasil | ~9,4 milhões |
| Em IES privadas (portais legados) | ~7,2 milhões (77%) |
| Mercado edtech Brasil | R$ 4-6 bilhões |
| Crescimento anual | 16-20% |
| Startups edtech BR | ~900 a 1.100 |
| Smartphone entre universitários | ~98% |

### 3.2 A Lacuna

Existe um vácuo entre:
- **Apps de IES** → funcionais mas UX horrível, sem IA, sem proatividade
- **Plataformas de estudo** (Passei Direto, Me Salva) → não integram com portal
- **Bots indie** → projetos amadores, não comerciais

**Ninguém está atacando esse espaço comercialmente no Brasil.**

### 3.3 Diferenciais Únicos do FAMus Bot

1. **IA contextual** — Nenhum competidor BR tem assistente IA que conhece sua grade, notas e rotina
2. **Notificação proativa** — Apps de IES são passivos; o aluno tem que entrar e verificar
3. **Telegram** — Sem instalar app, sem consumir armazenamento, leve
4. **Contexto de vida** — Ônibus, localização, horário de saída do trabalho
5. **Independente da IES** — Escala para qualquer faculdade com portal web

### 3.4 Riscos

| Risco | Severidade | Mitigação |
|---|---|---|
| Scraping é frágil (portal muda, quebra) | Alta | Monitoramento, modularização de parsers |
| Questões legais de scraping | Média | Usuário fornece próprias credenciais, LGPD compliance |
| IES bloqueiam scraping | Média | Rate limiting, negociação com IES |
| Escala de Chrome headless na VPS | Média | Migrar para requests + BS4 onde possível |
| Monetização B2C difícil (aluno não quer pagar) | Alta | Freemium agressivo, valor claro no premium |

---

## 4. Disposição de Pagamento

| Referência | Valor |
|---|---|
| Gasto médio com apps/assinaturas | R$ 30-60/mês (Spotify, Netflix, iFood) |
| Gasto com materiais de estudo digitais | R$ 15-40/mês |
| Disposição para app acadêmico pago | R$ 5-15/mês |
| Renda média universitário BR | R$ 1.200 a R$ 2.500/mês |
| Sensibilidade a preço | **Alta** — maioria prefere grátis |

---

## 5. Proposta de Precificação

### Modelo: Freemium com teste grátis de 7 dias do Pro

| Tier | Preço | Inclui |
|---|---|---|
| **Grátis** | R$ 0 | Consulta manual de notas e grade, 5 mensagens IA/dia, horários de ônibus |
| **Pro Semanal** | R$ 3,90/semana | Tudo do grátis + notificações automáticas de notas e faltas, IA ilimitada, alertas de risco de reprovação, cálculo de "quanto preciso tirar", resumo semanal |
| **Pro Mensal** | R$ 9,90/mês | Mesmo do semanal (economia de ~36%) |
| **Pro Semestral** | R$ 39,90/semestre | Mesmo do mensal (economia de ~33%) |

### Teste grátis
- 7 dias de Pro completo ao fazer cadastro
- Sem pedir cartão — vira Free automaticamente após 7 dias
- Objetivo: o aluno experimentar as notificações automáticas e a IA, sentir o valor, e converter

### Justificativa do preço
- **R$ 9,90/mês** está abaixo do Passei Direto (R$ 19,90) e muito abaixo do Me Salva! (R$ 34,90)
- Fica na faixa de "menos que um lanche" — argumento forte para universitário
- Opção semanal (R$ 3,90) reduz barreira de entrada: "menos de R$ 1 por dia"
- Semestral incentiva lock-in e reduz churn

### Projeção conservadora

| Cenário | Usuários | Conversão Pro | MRR |
|---|---|---|---|
| Inicial (FAM only) | 500 | 10% (50) | R$ 495/mês |
| Expansão (3-5 faculdades) | 5.000 | 7% (350) | R$ 3.465/mês |
| Escala (20+ faculdades) | 50.000 | 5% (2.500) | R$ 24.750/mês |

---

## 6. O que Construímos Hoje (26/02/2026)

### 6.1 Notificações automáticas de notas e faltas

**Problema:** O aluno só descobre que saiu nota quando entra no portal manualmente.

**Solução:** Job periódico que roda a cada 2 horas, faz scrape das notas de todos os usuários cadastrados, compara com o cache no banco, e envia notificação no Telegram se detectar mudanças.

**Arquivos modificados:**

- `src/db.py` — nova função `get_all_registered_users()`
- `src/monitor.py` — todo o sistema de verificação periódica:
  - `_comparar_notas()` — compara notas antigas vs novas, separa em mudanças de notas e mudanças de faltas
  - `_formatar_notificacao_nota()` — formata mensagem de notas
  - `_formatar_notificacao_faltas()` — formata mensagem de faltas (separada)
  - `_check_notas_usuario()` — faz scrape + comparação para um usuário
  - `job_verificar_atualizacoes()` — job async que itera todos os usuários
  - Registro do job no `main()` com `run_repeating(interval=7200, first=60)`

**Detalhes técnicos:**
- Scrape sequencial (não paralelo) para não sobrecarregar a VPS
- Sleep de 5s entre usuários
- Não notifica na primeira execução se cache vazio (evita spam)
- Atualiza cache no banco mesmo sem mudanças
- Falhas por usuário são logadas e não afetam os demais

**Formato das notificações:**

Notas:
```
📢 Atualização de notas!

📝 Engenharia de Software
   Saiu N1: 7.5
```

Faltas:
```
📋 Atualização de faltas!

📌 Engenharia de Software
   0 → 2/40 (5%)
```

### 6.2 Termos de uso no onboarding (LGPD compliance)

**Problema:** Precisamos de consentimento explícito do usuário para acessar o portal em seu nome.

**Solução:** Novo estado `TERMOS` no ConversationHandler, entre senha e confirmação.

**Arquivo modificado:** `src/cadastro.py`

**Fluxo:** nome → casa → trabalho → horário → login → senha → **termos** → confirmação

**Termos exibidos:**
```
📜 Termos de Uso — FAMus Bot

Ao continuar, você autoriza que o FAMus Bot:

1. Acesse o portal acadêmico da FAM em seu nome, usando as credenciais que você forneceu
2. Consulte periodicamente suas notas, faltas e grade para enviar notificações automáticas
3. Armazene seus dados de forma criptografada exclusivamente para o funcionamento do serviço

Seus dados nunca serão compartilhados com terceiros.
Você pode apagar tudo a qualquer momento com /resetar.
```

Se o usuário não aceitar, cadastro parcial é removido do banco.

---

## 7. Procedimentos de emergência

### Desativar notificações automáticas
Se o portal FAM mudar ou as notificações derem problema:
```bash
ssh -i ~/.ssh/jarvis-aws.pem ubuntu@3.85.203.235
# Editar monitor.py e comentar as 3 linhas do run_repeating no main()
sudo systemctl restart famus
```

### Forçar execução do job (debug)
Alterar `first=5` no `run_repeating` e reiniciar — roda em 5 segundos.

### Ver logs em tempo real
```bash
ssh -i ~/.ssh/jarvis-aws.pem ubuntu@3.85.203.235
sudo journalctl -u famus -f
```

### Checar se o job está rodando
Nos logs, procurar por:
```
Job notas: iniciando verificação periódica...
Job notas: X usuários registrados para verificar.
Job notas: verificação concluída.
```

### Rollback completo
Os arquivos anteriores ao deploy estão no git local:
```bash
cd /home/pedro/faculdade/jarvis
git diff HEAD src/db.py src/monitor.py src/cadastro.py  # ver mudanças
git checkout HEAD -- src/db.py src/monitor.py src/cadastro.py  # reverter
# depois fazer deploy normal via SCP
```

---

## 8. Próximas features planejadas (alto valor para premium)

1. **"Quanto preciso tirar pra passar?"** — Cálculo automático da nota mínima necessária na N2/N3 para aprovação
2. **Alerta de risco de reprovação por falta** — Projeção inteligente baseada em faltas atuais vs limite
3. **Resumo semanal automático** — Briefing domingo à noite com aulas, prazos, riscos e notas necessárias
