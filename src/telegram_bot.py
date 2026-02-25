"""
Telegram Bot para enviar notificações
"""

from telegram import Bot
from telegram.error import TelegramError, TimedOut
import logging
import asyncio

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, bot_token, chat_id, bot=None, connect_timeout=20.0, read_timeout=20.0):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.bot = bot
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout

    def _init_bot(self):
        """Inicializa o bot do Telegram"""
        if not self.bot:
            self.bot = Bot(token=self.bot_token)

    async def enviar_mensagem(self, mensagem):
        """Envia uma mensagem simples"""
        self._init_bot()

        for tentativa in range(1, 3):
            try:
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=mensagem,
                    parse_mode='Markdown',
                    read_timeout=self.read_timeout,
                    connect_timeout=self.connect_timeout
                )
                logger.info("Mensagem enviada com sucesso")
                return True
            except TimedOut as e:
                logger.warning(
                    "Timeout ao enviar mensagem para o Telegram (tentativa %d): %s",
                    tentativa,
                    e
                )
                if tentativa == 2:
                    logger.error("Falha ao enviar mensagem após tentativas com timeout")
                    return False
                await asyncio.sleep(2)
            except TelegramError as e:
                logger.error(f"Erro ao enviar mensagem: {e}")
                return False

    def _escapar_markdown(self, texto):
        """Escapa caracteres especiais do Markdown"""
        if not texto:
            return ""
        # Conjunto mínimo de caracteres que quebram a sintaxe Markdown
        caracteres_especiais = ['_', '*', '[', ']', '(', ')', '~', '`']
        for char in caracteres_especiais:
            texto = texto.replace(char, f'\\{char}')
        return texto

    def _formatar_materiais(self, materiais):
        """Formata lista de materiais para exibição no Telegram"""
        if not materiais:
            return "_Nenhum material disponível._"

        linhas = []
        for material in materiais:
            nome = self._escapar_markdown(material.get('nome', 'N/A'))
            tipo = self._escapar_markdown(material.get('tipo', '').strip())
            link = self._escapar_markdown(material.get('link', '').strip())

            partes = [nome]
            if tipo:
                partes.append(f"({tipo})")

            linha = " ".join(partes)
            if link:
                linha = f"{linha}\n  {link}"

            linhas.append(f"- {linha}")

        return "\n".join(linhas)

    def _montar_texto_atividade(self, atividade, cabecalho):
        """Gera texto completo de uma atividade"""
        titulo = self._escapar_markdown(atividade.get('titulo', 'N/A'))
        disciplina = self._escapar_markdown(atividade.get('disciplina', 'N/A'))
        professor = self._escapar_markdown(atividade.get('professor', 'N/A'))
        periodo = self._escapar_markdown(atividade.get('periodo', 'N/A'))
        tipo = self._escapar_markdown(atividade.get('tipo', 'N/A'))
        situacao_raw = (atividade.get('situacao', 'N/A') or "").replace('\n', ' ')
        situacao = self._escapar_markdown(situacao_raw)
        prazo_raw = (atividade.get('prazo', 'N/A') or "").replace('\n', ' ')
        prazo = self._escapar_markdown(prazo_raw)
        descricao = self._escapar_markdown(atividade.get('descricao', 'N/A'))
        link = self._escapar_markdown(atividade.get('link', 'N/A'))
        materiais = self._formatar_materiais(atividade.get('materiais', []))

        mensagem = f"""
{cabecalho}

📚 *Disciplina:* {disciplina}
📝 *Título:* {titulo}
👨‍🏫 *Professor:* {professor}
📅 *Período:* {periodo}
📋 *Tipo:* {tipo}
📊 *Situação:* {situacao}
⏰ *Prazo:* {prazo}

📄 *Descrição:*
{descricao}

📂 *Materiais:*
{materiais}

🔗 Link: {link}
        """
        return mensagem.strip()

    async def notificar_nova_atividade(self, atividade):
        """Envia notificação formatada de nova atividade"""
        mensagem = self._montar_texto_atividade(
            atividade,
            "🆕 *Nova Atividade Detectada*"
        )
        return await self.enviar_mensagem(mensagem)

    async def notificar_resumo(self, atividades, novas_atividades):
        """Envia resumo do monitoramento com lista de atividades"""
        total_atividades = len(atividades)

        mensagem_header = (
            "📊 *Resumo do Monitoramento*\n\n"
            f"Total de atividades: {total_atividades}\n"
            f"Novas atividades: {len(novas_atividades)}"
        )
        await self.enviar_mensagem(mensagem_header)

        if not atividades:
            return True

        for idx, atividade in enumerate(atividades, 1):
            cabecalho = f"📌 *Atividade {idx}*"
            mensagem = self._montar_texto_atividade(atividade, cabecalho)
            await self.enviar_mensagem(mensagem)
            await asyncio.sleep(1)

        return True


if __name__ == "__main__":
    # Teste do bot
    import asyncio
    import os
    from dotenv import load_dotenv

    logging.basicConfig(level=logging.INFO)
    load_dotenv()

    async def test():
        notifier = TelegramNotifier(
            bot_token=os.getenv('TELEGRAM_BOT_TOKEN'),
            chat_id=os.getenv('TELEGRAM_CHAT_ID')
        )

        await notifier.enviar_mensagem("🤖 Bot FAM Monitor - Teste de conexão")

    asyncio.run(test())
