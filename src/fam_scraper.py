"""
Scraper para o Portal FAM
Responsável por fazer login e extrair atividades
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup
import logging
import os
import re
import time
import unicodedata

logger = logging.getLogger(__name__)


class FAMScraper:
    def __init__(self, login, senha, headless=True):
        self.login = login
        self.senha = senha
        self.headless = headless
        self.driver = None

    def _setup_driver(self):
        """Configura o driver do Selenium"""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')

        self.driver = webdriver.Chrome(options=chrome_options)
        logger.info("Driver do Chrome configurado")

    def fazer_login(self):
        """Faz login no portal FAM"""
        try:
            self._setup_driver()
            logger.info("Acessando portal FAM...")
            self.driver.get("https://www.famportal.com.br/")

            # Aguarda a página carregar
            wait = WebDriverWait(self.driver, 20)

            # Localiza e preenche o campo de login (usando name ao invés de id)
            logger.info("Preenchendo credenciais...")
            login_field = wait.until(
                EC.presence_of_element_located((By.NAME, "user"))
            )
            login_field.clear()
            login_field.send_keys(self.login)

            # Localiza e preenche o campo de senha (usando name ao invés de id)
            senha_field = self.driver.find_element(By.NAME, "senha")
            senha_field.clear()
            senha_field.send_keys(self.senha)

            # Clica no botão de login (usando name ao invés de CSS selector)
            login_button = self.driver.find_element(By.NAME, "login")
            login_button.click()

            # Aguarda o login completar (aumentado para 5 segundos)
            time.sleep(5)

            # Verifica se o login foi bem sucedido
            if "portal" in self.driver.current_url.lower() or "pg_portal" in self.driver.current_url:
                logger.info("Login realizado com sucesso")
                return True
            else:
                logger.error("Login falhou - URL não mudou")
                return False

        except TimeoutException:
            logger.error("Timeout ao tentar fazer login - página não carregou")
            return False
        except Exception as e:
            logger.error(f"Erro ao fazer login: {e}", exc_info=True)
            return False

    def navegar_para_atividades(self):
        """Navega até a página de atividades"""
        try:
            wait = WebDriverWait(self.driver, 10)

            # Procura pelo link de "Atividades" no menu
            logger.info("Navegando para página de atividades...")

            try:
                atividades_link = wait.until(
                    EC.element_to_be_clickable((
                        By.XPATH,
                        "//a[contains(@href, 'atividades=X')]"
                    ))
                )
                atividades_link.click()
            except TimeoutException:
                logger.warning("Link de atividades não encontrado - acessando URL diretamente")
                self.driver.get(
                    "https://www.famportal.com.br/fam/pg_portal.php?frame=frame_avisos.php&atividades=X"
                )

            # Aguarda página carregar
            time.sleep(3)

            try:
                wait.until(lambda drv: "atividades=X" in drv.current_url.lower())
            except TimeoutException:
                logger.warning("Timeout ao confirmar URL de atividades - seguindo mesmo assim")
            logger.info("Página de atividades carregada")
            return True

        except Exception as e:
            logger.error(f"Erro ao navegar para atividades: {e}")
            return False

    def extrair_atividades(self):
        """Extrai lista de atividades do portal"""
        try:
            atividades = []

            logger.info("Extraindo atividades...")

            # Navega para página de atividades
            if not self.navegar_para_atividades():
                logger.error("Não foi possível acessar a página de atividades")
                return atividades

            # Aguarda a página carregar
            time.sleep(2)

            # Salva screenshot para debug
            self.driver.save_screenshot(os.path.join(os.path.dirname(__file__), '..', 'logs', 'debug_screenshot.png'))
            logger.info("Screenshot salvo em logs/debug_screenshot.png")

            # Busca todas as linhas de atividades (tr com class lovelyrow1 ou lovelyrow2)
            linhas_atividades = self.driver.find_elements(
                By.XPATH,
                "//tr[@class='lovelyrow1' or @class='lovelyrow2']"
            )

            logger.info(f"Encontradas {len(linhas_atividades)} atividades")

            for linha in linhas_atividades:
                try:
                    # Extrai o título (primeira td > table > tr > td)
                    titulo_elem = linha.find_element(By.XPATH, ".//td[@class='nicepadding'][1]//td[@width='95%']")
                    titulo = titulo_elem.text.strip()

                    # Extrai informações detalhadas (professor, período, disciplina)
                    info_elem = linha.find_element(By.XPATH, ".//td[@class='MensagensAtv']")
                    info_texto = info_elem.text.strip()

                    # Parseia as informações
                    professor = ""
                    periodo = ""
                    disciplina = ""

                    if "Criado por:" in info_texto:
                        parts = info_texto.split("||")
                        if len(parts) >= 1:
                            professor = parts[0].replace("Criado por:", "").strip()
                        if len(parts) >= 2:
                            periodo = parts[1].replace("Período de Vigência:", "").strip()

                    # Extrai disciplina (da linha seguinte)
                    try:
                        disc_elem = linha.find_element(By.XPATH, ".//td[@class='Mensagens'][@width='95%']")
                        disciplina = disc_elem.text.strip()
                    except:
                        pass

                    # Extrai tipo de atividade
                    tipo_elem = linha.find_element(By.XPATH, ".//td[@class='nicepadding'][2]//td[1]")
                    tipo_atividade = tipo_elem.text.strip()

                    # Extrai situação
                    situacao_elem = linha.find_element(By.XPATH, ".//td[@class='nicepadding'][2]//td[@class='MensagensAtv']")
                    situacao = situacao_elem.text.strip()

                    # Extrai prazo
                    prazo_elem = linha.find_element(By.XPATH, ".//td[@class='nicepadding'][3]//div")
                    prazo_texto = prazo_elem.text.strip()

                    # Extrai link da atividade
                    link_onclick = linha.get_attribute("onclick")
                    link = ""
                    if link_onclick and "location.href=" in link_onclick:
                        link = link_onclick.split("'")[1]
                        if not link.startswith("http"):
                            link = f"https://www.famportal.com.br/fam/{link}"

                    # Cria objeto da atividade
                    atividade = {
                        "titulo": titulo,
                        "disciplina": disciplina,
                        "professor": professor,
                        "periodo": periodo,
                        "tipo": tipo_atividade,
                        "situacao": situacao,
                        "prazo": prazo_texto,
                        "link": link
                    }

                    detalhes = self.extrair_detalhes_atividade(link)
                    atividade.update(detalhes)

                    atividades.append(atividade)
                    logger.info(f"Atividade extraída: {titulo}")

                except Exception as e:
                    logger.warning(f"Erro ao extrair atividade individual: {e}")
                    continue

            logger.info(f"Total de atividades extraídas: {len(atividades)}")
            return atividades

        except Exception as e:
            logger.error(f"Erro ao extrair atividades: {e}", exc_info=True)
            return []

    def _normalizar_texto(self, texto):
        """Remove acentos e normaliza texto para comparação"""
        if not texto:
            return ""
        texto_norm = unicodedata.normalize('NFKD', texto)
        texto_ascii = texto_norm.encode('ASCII', 'ignore').decode('ASCII')
        return texto_ascii.lower().strip()

    def extrair_detalhes_atividade(self, link):
        """Abre a página da atividade para capturar descrição e materiais"""
        detalhes = {
            "descricao": "",
            "materiais": []
        }

        if not link:
            return detalhes

        original_window = self.driver.current_window_handle
        original_handles = self.driver.window_handles.copy()
        html_conteudo = ""

        try:
            self.driver.execute_script("window.open(arguments[0], '_blank');", link)
            WebDriverWait(self.driver, 20).until(
                lambda drv: len(drv.window_handles) > len(original_handles)
            )

            nova_janela = [h for h in self.driver.window_handles if h not in original_handles]
            if not nova_janela:
                logger.warning("Não foi possível identificar nova janela da atividade")
                return detalhes

            self.driver.switch_to.window(nova_janela[0])
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(1)  # breve espera para garantir renderização
            html_conteudo = self.driver.page_source

        except Exception as e:
            logger.warning(f"Erro ao carregar detalhes da atividade: {e}")
        finally:
            try:
                if self.driver.current_window_handle != original_window:
                    self.driver.close()
                    WebDriverWait(self.driver, 10).until(
                        lambda drv: len(drv.window_handles) == len(original_handles)
                    )
                    self.driver.switch_to.window(original_window)
            except Exception as e:
                logger.warning(f"Erro ao retornar para janela original: {e}")

        if not html_conteudo:
            return detalhes

        soup = BeautifulSoup(html_conteudo, "html.parser")

        # Descrição da atividade
        descricao = ""
        for td in soup.find_all("td"):
            linhas = [linha.strip() for linha in td.get_text(separator="\n").splitlines()]
            linhas = [linha for linha in linhas if linha]
            if not linhas:
                continue

            capturando = False
            coletadas = []

            for linha in linhas:
                linha_norm = self._normalizar_texto(linha)

                if not capturando and "descricao da atividade" in linha_norm:
                    capturando = True
                    continue

                if capturando:
                    if "material associado" in linha_norm:
                        break
                    coletadas.append(linha)

            if coletadas:
                descricao = "\n".join(coletadas).strip()
                break

        detalhes["descricao"] = descricao

        # Materiais associados
        materiais = []
        for input_tag in soup.select("input[name='mat_link']"):
            link_material = (input_tag.get("value") or "").strip()
            linha = input_tag.find_parent("tr")
            if not linha:
                continue

            colunas = linha.find_all("td")
            if not colunas:
                continue

            nome_material = colunas[0].get_text(separator=" ", strip=True) if len(colunas) >= 1 else ""
            tipo_material = colunas[1].get_text(separator=" ", strip=True) if len(colunas) >= 2 else ""

            if link_material:
                materiais.append({
                    "nome": nome_material,
                    "tipo": tipo_material,
                    "link": link_material
                })

        # Remove duplicados mantendo ordem
        vistos = set()
        materiais_unicos = []
        for material in materiais:
            chave = material["link"]
            if chave in vistos:
                continue
            vistos.add(chave)
            materiais_unicos.append(material)

        detalhes["materiais"] = materiais_unicos
        return detalhes

    def extrair_notas(self):
        """Navega até a página de notas e extrai boletim + info do aluno.

        Retorna (notas_list, info_aluno_dict) ou (None, None) em caso de erro.
        """
        try:
            logger.info("Navegando para página de notas...")
            self.driver.get(
                "https://www.famportal.com.br/fam/pg_portal.php?"
                "frame=frame_alu_notas.php&slc=X&frame_notas=frame_alu_notas_resultados.php"
            )
            time.sleep(3)

            html = self.driver.page_source

            # Salva HTML para debug/análise
            debug_path = os.path.join(os.path.dirname(__file__), '..', 'logs', 'notas_debug.html')
            os.makedirs(os.path.dirname(debug_path), exist_ok=True)
            with open(debug_path, 'w', encoding='utf-8') as f:
                f.write(html)
            logger.info("HTML de notas salvo em %s", debug_path)

            notas = parse_notas_html(html)
            info = parse_info_aluno(html)
            logger.info("Notas extraídas: %s | Info: %s", len(notas) if notas else 0, info)
            return notas, info

        except Exception as e:
            logger.error("Erro ao extrair notas: %s", e, exc_info=True)
            return None, None

    def extrair_grade(self):
        """Navega até a página de grade e extrai a grade horária."""
        try:
            logger.info("Navegando para página de grade horária...")
            self.driver.get(
                "https://www.famportal.com.br/fam/pg_portal.php?frame=frame_alu_gradealuno.php"
            )
            time.sleep(3)

            html = self.driver.page_source
            grade = parse_grade_html(html)
            logger.info("Grade extraída: %s", {k: len(v) for k, v in grade.items()})
            return grade

        except Exception as e:
            logger.error("Erro ao extrair grade: %s", e, exc_info=True)
            return None

    def close(self):
        """Fecha o navegador"""
        if self.driver:
            self.driver.quit()
            logger.info("Driver fechado")


# ── Mapeamento aulas → horários (noturno FAM) ──────────────────────────────

HORARIOS = {
    "P1": ("", ""),          # horário variável (sábado / ativ. complementar)
    "01": ("19:00", "19:50"),
    "02": ("19:50", "20:40"),
    "03": ("20:50", "21:40"),
    "04": ("21:40", "22:30"),
}

# Colunas da tabela: SEG=0, TER=1, QUA=2, QUI=3, SEX=4, SAB=5
COLUNAS_DIA = {1: "0", 2: "1", 3: "2", 4: "3", 5: "4", 6: "5"}


def parse_grade_html(html: str) -> dict:
    """Parseia HTML da página de grade e retorna dict no formato do banco.

    Estrutura real do portal:
      <table class="Grade">
        <tbody>
          <tr> header (Descricoes) </tr>
          <tr>  ← row por aula (P1, 01, 02, 03, 04)
            <td class="GradeNotas">01</td>           ← label da aula
            <td class="GradeNotas">                   ← célula do dia (SEG, TER, ...)
              <table>
                <tr><td class="LinhaPar">dados</td></tr>   ← matéria dentro
              </table>
            </td>
            ...
          </tr>
        </tbody>
      </table>

    Retorno: {"0": [{"materia": ..., "prof": ..., "inicio": ..., "fim": ...}], ...}
    """
    soup = BeautifulSoup(html, "html.parser")
    tabela = soup.find("table", class_="Grade")
    if not tabela:
        logger.warning("Tabela de grade não encontrada no HTML")
        return {str(d): [] for d in range(6)}

    # Pega só as <tr> diretas da tabela (ignora <tr> de tabelas aninhadas)
    tbody = tabela.find("tbody") or tabela
    linhas = tbody.find_all("tr", recursive=False)
    if len(linhas) < 2:
        logger.warning("Tabela de grade sem linhas de dados")
        return {str(d): [] for d in range(6)}

    # grade_crua: {dia_str: [(aula_label, materia, prof), ...]}
    grade_crua = {str(d): [] for d in range(6)}

    # Pula header (primeira linha)
    for linha in linhas[1:]:
        # Pega só <td> diretos da row (class="GradeNotas")
        celulas = linha.find_all("td", recursive=False)
        if not celulas:
            continue

        # Primeira célula = label da aula (P1, 01, 02, 03, 04)
        aula_label = celulas[0].get_text(strip=True)
        if aula_label not in HORARIOS:
            continue

        # Células restantes: SEG(1), TER(2), QUA(3), QUI(4), SEX(5), SAB(6)
        for col_idx in range(1, min(len(celulas), 7)):
            dia_str = COLUNAS_DIA.get(col_idx)
            if dia_str is None:
                continue

            celula = celulas[col_idx]

            # Procura matérias DENTRO da célula (em tabelas aninhadas)
            inner_tds = celula.find_all("td", class_=["LinhaPar", "LinhaImpar"])
            for inner_td in inner_tds:
                materia, prof = _extrair_celula(inner_td)
                if materia:
                    grade_crua[dia_str].append((aula_label, materia, prof))

    # Agrupa slots consecutivos com mesma matéria por dia
    return _agrupar_grade(grade_crua)


def _extrair_celula(celula) -> tuple[str, str]:
    """Extrai (matéria, professor) de uma célula da grade.

    Estrutura esperada:
        NomeMatéria<br><br>
        <font class="MensagensAtv">NomeProfessor(ID)<br><br></font>
        TurmaCódigo[ID]<br><br>
        <font class="MensagensAtv">Curso</font>
    """
    texto = celula.get_text(separator="\n", strip=True)
    if not texto:
        return "", ""

    # Divide o texto por linhas e remove vazias
    partes = [p.strip() for p in texto.splitlines() if p.strip()]
    if not partes:
        return "", ""

    materia = _limpar_nome_materia(partes[0])

    # Professor: segunda parte, remover ID numérico entre parênteses
    prof = ""
    if len(partes) > 1:
        prof_raw = partes[1]
        # Remove "(123)" do final
        prof = re.sub(r"\s*\(\d+\)\s*$", "", prof_raw).strip()

    return materia, prof


def _limpar_nome_materia(nome: str) -> str:
    """Remove sufixo de curso do nome da matéria.

    Ex: 'Atividades de Extensão IV - Ciência da Computação' → 'Atividades de Extensão IV'
    """
    # Remove ' - NomeDoCurso' do final
    return re.sub(r"\s*-\s*(?:Ciência da Computação|Engenharia|Administração|Direito|Pedagogia).*$", "", nome).strip()


def _agrupar_grade(grade_crua: dict) -> dict:
    """Agrupa slots por matéria e calcula início/fim de cada bloco.

    Lida com múltiplas matérias no mesmo slot (ex: Extensão + Tópicos na aula 03-04).
    """
    ordem_aulas = ["P1", "01", "02", "03", "04"]

    resultado = {}
    for dia, slots in grade_crua.items():
        if not slots:
            resultado[dia] = []
            continue

        # Agrupa por matéria: {materia: (prof, [aula_labels])}
        materias = {}
        for aula_label, materia, prof in slots:
            if materia not in materias:
                materias[materia] = (prof, [])
            if aula_label not in materias[materia][1]:
                materias[materia][1].append(aula_label)

        # Cria blocos com início/fim baseado na primeira e última aula
        blocos = []
        for materia, (prof, aulas) in materias.items():
            aulas.sort(key=lambda a: ordem_aulas.index(a) if a in ordem_aulas else 99)
            inicio = HORARIOS.get(aulas[0], ("", ""))[0]
            fim = HORARIOS.get(aulas[-1], ("", ""))[1]
            blocos.append({"materia": materia, "prof": prof, "inicio": inicio, "fim": fim})

        # Ordena por horário de início
        blocos.sort(key=lambda b: b["inicio"])
        resultado[dia] = blocos

    return resultado


# ── Parser de info do aluno ──────────────────────────────────────────────────


def parse_info_aluno(html: str) -> dict | None:
    """Extrai informações do aluno da página de notas/resultados.

    Retorno: {"curso": str, "semestre": str, "turma": str, "sala": str}
    """
    soup = BeautifulSoup(html, "html.parser")
    info = {}

    # Turma e Localização: <font class="login-u">57-05-B</font> e <font class="login-u">Bloco 2 - Sala 073...</font>
    login_u_tags = soup.find_all("font", class_="login-u")
    for tag in login_u_tags:
        texto = tag.get_text(strip=True)
        # Turma no formato XX-YY-Z (código_curso-série-letra)
        if re.match(r"^\d+-\d+-\w$", texto):
            partes = texto.split("-")
            info["turma_codigo"] = texto
            if len(partes) >= 2:
                info["semestre"] = str(int(partes[1]))  # "05" → "5"
        # Localização (Bloco / Sala)
        if "Bloco" in texto or "Sala" in texto:
            info["sala"] = texto

    # Curso: tabela com Curso | (vazio) | Série | Turma seguida de dados
    for td in soup.find_all("td", class_="LinhaPar"):
        texto = td.get_text(strip=True)
        if "Computação" in texto or "Engenharia" in texto or "Administração" in texto or "Direito" in texto:
            info["curso"] = texto
            break

    return info if info else None


# ── Parser de notas ──────────────────────────────────────────────────────────


def _parse_nota_valor(texto: str) -> float | None:
    """Converte texto de nota para float. Retorna None se vazio ou inválido."""
    texto = texto.strip().replace(",", ".")
    if not texto or texto in ("-", "--", ""):
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def parse_notas_html(html: str) -> list[dict] | None:
    """Parseia HTML da página de notas (aba Resultados) do portal FAM.

    Estrutura da tabela (class="GradeNotas"):
      Colunas: Código | Disciplina | N1 | Peso | MP1 | N2 | Peso | MP2 |
               N3 | Peso | MP3 | MS | AR_elig | AR | MF | MaxFaltas | Faltas
      (17 <td> por linha, ou 12 quando N2/N3 "Não disponível" com colspan=6)

    Retorno: [{"disciplina": str, "n1": float|None, "n2": float|None,
               "n3": float|None, "media_semestral": float|None,
               "media_final": float|None, "faltas": int, "max_faltas": int}, ...]
    """
    soup = BeautifulSoup(html, "html.parser")
    tabela = soup.find("table", class_="GradeNotas")
    if not tabela:
        logger.warning("Tabela GradeNotas não encontrada no HTML")
        return None

    notas = []
    for row in tabela.find_all("tr"):
        tds = row.find_all("td")
        if len(tds) < 10:
            continue

        # Linhas de dados começam com código numérico na primeira célula
        codigo = tds[0].get_text(strip=True)
        if not codigo.isdigit():
            continue

        disciplina = _limpar_nome_materia(tds[1].get_text(strip=True))

        # Verifica se N2/N3 estão disponíveis (colspan "Não disponível")
        nao_disponivel = any("Não disponível" in td.get_text() for td in tds)

        # N1 sempre na posição 2
        n1 = _parse_nota_valor(tds[2].get_text(strip=True))

        # N2 e N3 dependem de disponibilidade
        n2 = None
        n3 = None
        if not nao_disponivel and len(tds) >= 17:
            n2 = _parse_nota_valor(tds[5].get_text(strip=True))
            n3 = _parse_nota_valor(tds[8].get_text(strip=True))

        # MS (Média Semestral) — classe única ColunaMP
        ms_td = row.find("td", class_="ColunaMP")
        ms = _parse_nota_valor(ms_td.get_text(strip=True)) if ms_td else None

        # MF (Média Final) — classe única ColunaMF
        mf_td = row.find("td", class_="ColunaMF")
        mf = _parse_nota_valor(mf_td.get_text(strip=True)) if mf_td else None

        # Faltas e máximo (duas últimas células)
        faltas_text = tds[-1].get_text(strip=True)
        max_faltas_text = tds[-2].get_text(strip=True)
        faltas = int(faltas_text) if faltas_text.isdigit() else 0
        max_faltas = int(max_faltas_text) if max_faltas_text.isdigit() else 0

        notas.append({
            "disciplina": disciplina,
            "n1": n1,
            "n2": n2,
            "n3": n3,
            "media_semestral": ms,
            "media_final": mf,
            "faltas": faltas,
            "max_faltas": max_faltas,
        })

    if not notas:
        logger.warning("Nenhuma nota encontrada — verifique logs/notas_debug.html")
        return None

    return notas


if __name__ == "__main__":
    # Teste manual do scraper
    import os
    from dotenv import load_dotenv

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    load_dotenv()

    scraper = FAMScraper(
        login=os.getenv('FAM_LOGIN'),
        senha=os.getenv('FAM_SENHA'),
        headless=False  # Mostra o navegador para debug
    )

    try:
        if scraper.fazer_login():
            print("Login OK!")
            atividades = scraper.extrair_atividades()
            print(f"Atividades encontradas: {len(atividades)}")
        else:
            print("Falha no login")
    finally:
        input("Pressione Enter para fechar o navegador...")
        scraper.close()
