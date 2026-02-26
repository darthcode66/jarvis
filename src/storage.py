"""
Sistema de persistência de dados
Armazena histórico de atividades para detectar novas
"""

import json
import os
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class Storage:
    def __init__(self, data_file=os.path.join(os.path.dirname(__file__), '..', 'data', 'atividades.json')):
        self.data_file = data_file
        self._ensure_data_file()

    def _ensure_data_file(self):
        """Garante que o arquivo de dados existe"""
        if not os.path.exists(self.data_file):
            self._save_data({"atividades": [], "last_check": None})
            logger.info(f"Arquivo de dados criado: {self.data_file}")

    def _load_data(self):
        """Carrega dados do arquivo JSON"""
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Erro ao carregar dados: {e}")
            return {"atividades": [], "last_check": None}

    def _save_data(self, data):
        """Salva dados no arquivo JSON"""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("Dados salvos com sucesso")
        except Exception as e:
            logger.error(f"Erro ao salvar dados: {e}")

    def get_atividades(self):
        """Retorna lista de atividades armazenadas"""
        data = self._load_data()
        return data.get("atividades", [])

    def adicionar_atividade(self, atividade):
        """Adiciona uma nova atividade"""
        data = self._load_data()

        # Adiciona timestamp
        atividade['discovered_at'] = datetime.now().isoformat()

        data["atividades"].append(atividade)
        self._save_data(data)
        logger.info(f"Atividade adicionada: {atividade.get('titulo', 'N/A')}")

    def atualizar_last_check(self):
        """Atualiza timestamp da última verificação"""
        data = self._load_data()
        data["last_check"] = datetime.now().isoformat()
        self._save_data(data)

    def is_nova_atividade(self, atividade):
        """Verifica se a atividade é nova (não está no histórico)"""
        atividades_existentes = self.get_atividades()

        # Cria um identificador único baseado em título + disciplina
        novo_id = f"{atividade.get('titulo', '')}_{atividade.get('disciplina', '')}"

        for at in atividades_existentes:
            existing_id = f"{at.get('titulo', '')}_{at.get('disciplina', '')}"
            if novo_id == existing_id:
                return False

        return True

    def get_novas_atividades(self, atividades_atuais):
        """Compara atividades atuais com histórico e retorna as novas"""
        novas = []

        for atividade in atividades_atuais:
            if self.is_nova_atividade(atividade):
                novas.append(atividade)
                self.adicionar_atividade(atividade)

        return novas

    def get_stats(self):
        """Retorna estatísticas do storage"""
        data = self._load_data()
        return {
            "total_atividades": len(data.get("atividades", [])),
            "last_check": data.get("last_check"),
        }


if __name__ == "__main__":
    # Teste do storage
    logging.basicConfig(level=logging.INFO)

    storage = Storage()

    # Teste adicionando uma atividade
    atividade_teste = {
        "titulo": "Trabalho de Teste",
        "disciplina": "Matemática",
        "prazo": "2025-11-01",
        "descricao": "Descrição teste"
    }

    if storage.is_nova_atividade(atividade_teste):
        print("Nova atividade detectada!")
        storage.adicionar_atividade(atividade_teste)
    else:
        print("Atividade já existe")

    print(f"\nEstatísticas: {storage.get_stats()}")
