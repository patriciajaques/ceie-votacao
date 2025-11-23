import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta, timezone
import os
import shutil
from pathlib import Path
from io import StringIO, BytesIO
from PIL import Image
import numpy as np
from collections import Counter
import json

# Dropbox API imports
try:
    import dropbox
    from dropbox.exceptions import ApiError, AuthError
    DROPBOX_AVAILABLE = True
except ImportError:
    DROPBOX_AVAILABLE = False

# --- Configuração da Página ---
st.set_page_config(page_title="Eleição CEIE", page_icon="🗳️", layout="centered")

# --- Constantes e Configurações ---
DB_FILE = 'votos.db'
ARQUIVO_ELEITORES = 'eleitores.csv'
ARQUIVO_CANDIDATOS = 'candidatos.csv'
EMAIL_ADMIN = st.secrets.get("EMAIL_ADMIN", "admin@ceie.com")
SENHA_ADMIN = st.secrets.get("PASSWORD_ADMIN", "admin123")
MAX_SELECTIONS = int(st.secrets.get("MAX_SELECTIONS", 3))
LOGO_PATH = Path('logo')

# Dropbox Configuration
DROPBOX_CONFIG = st.secrets.get("DROPBOX", {})
DROPBOX_ACCESS_TOKEN = DROPBOX_CONFIG.get("ACCESS_TOKEN", "")
DROPBOX_FOLDER = DROPBOX_CONFIG.get("FOLDER", "/CEIE Votacao Backups")  # Pasta no Dropbox
DROPBOX_FILE_NAME = "votos_ceie.db"  # Nome do arquivo
# Caminho completo: pasta + arquivo
DROPBOX_FILE_PATH = f"{DROPBOX_FOLDER.rstrip('/')}/{DROPBOX_FILE_NAME}"
UPLOAD_INTERVAL_MINUTES = 15  # Intervalo para upload periódico

# --- Funções Auxiliares para Leitura de CSVs ---
def ler_csv_eleitores():
    """Lê o CSV de eleitores do arquivo ou dos secrets."""
    try:
        # Tenta ler do arquivo primeiro
        if os.path.exists(ARQUIVO_ELEITORES):
            return pd.read_csv(ARQUIVO_ELEITORES)
        # Se não existir, tenta ler dos secrets
        elif 'ELEITORES_CSV' in st.secrets:
            return pd.read_csv(StringIO(st.secrets['ELEITORES_CSV']))
        else:
            raise FileNotFoundError(
                f"Arquivo '{ARQUIVO_ELEITORES}' não encontrado e "
                "secret 'ELEITORES_CSV' não configurado."
            )
    except Exception as e:
        st.error(f"Erro ao carregar eleitores: {e}")
        raise

def ler_csv_candidatos():
    """Lê o CSV de candidatos do arquivo ou dos secrets."""
    try:
        # Tenta ler do arquivo primeiro
        if os.path.exists(ARQUIVO_CANDIDATOS):
            return pd.read_csv(ARQUIVO_CANDIDATOS)
        # Se não existir, tenta ler dos secrets
        elif 'CANDIDATOS_CSV' in st.secrets:
            return pd.read_csv(StringIO(st.secrets['CANDIDATOS_CSV']))
        else:
            raise FileNotFoundError(
                f"Arquivo '{ARQUIVO_CANDIDATOS}' não encontrado e "
                "secret 'CANDIDATOS_CSV' não configurado."
            )
    except Exception as e:
        st.error(f"Erro ao carregar candidatos: {e}")
        raise

# --- Funções de Banco de Dados (SQLite) ---
def init_db():
    """Inicializa o banco de dados e tabela de configuração se não existirem."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Tabela de Votos (user_id é Chave Primária para permitir atualização de voto)
    c.execute('''
        CREATE TABLE IF NOT EXISTS votos (
            user_id TEXT PRIMARY KEY,
            escolhas TEXT,
            timestamp DATETIME
        )
    ''')
    
    # Tabela de Configuração (Estado da Votação)
    c.execute('''
        CREATE TABLE IF NOT EXISTS config (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
    ''')
    
    # Define estado inicial como ABERTO se não existir
    c.execute("INSERT OR IGNORE INTO config (chave, valor) VALUES ('status', 'ABERTO')")
    
    # Inicializa campo de último upload do Dropbox (se não existir)
    c.execute("INSERT OR IGNORE INTO config (chave, valor) VALUES ('ultimo_upload_dropbox', '')")
    
    # Inicializa título da votação com valor padrão
    c.execute("INSERT OR IGNORE INTO config (chave, valor) VALUES ('titulo_votacao', 'Eleição CEIE')")
    
    # Inicializa número máximo de seleções com valor padrão de secrets
    max_selections_default = str(int(st.secrets.get("MAX_SELECTIONS", 3)))
    c.execute("INSERT OR IGNORE INTO config (chave, valor) VALUES ('max_selections', ?)", (max_selections_default,))
    
    conn.commit()
    conn.close()

def get_voting_status():
    conn = sqlite3.connect(DB_FILE)
    status = conn.cursor().execute("SELECT valor FROM config WHERE chave='status'").fetchone()[0]
    conn.close()
    return status

def set_voting_status(new_status):
    conn = sqlite3.connect(DB_FILE)
    conn.cursor().execute("UPDATE config SET valor = ? WHERE chave='status'", (new_status,))
    conn.commit()
    conn.close()
    
    # Upload imediato para Dropbox ao mudar status
    upload_db_to_dropbox()

def get_titulo_votacao():
    """Lê título da votação da tabela config, retorna 'Eleição CEIE' como padrão se não existir."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    result = c.execute("SELECT valor FROM config WHERE chave='titulo_votacao'").fetchone()
    conn.close()
    if result and result[0]:
        return result[0]
    return "Eleição CEIE"

def set_titulo_votacao(titulo):
    """Salva título da votação na tabela config."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)", ('titulo_votacao', titulo))
    conn.commit()
    conn.close()

def get_max_selections():
    """Lê número máximo de seleções da tabela config, retorna valor de st.secrets como fallback."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    result = c.execute("SELECT valor FROM config WHERE chave='max_selections'").fetchone()
    conn.close()
    if result and result[0]:
        try:
            return int(result[0])
        except (ValueError, TypeError):
            pass
    # Fallback para secrets
    return int(st.secrets.get("MAX_SELECTIONS", 3))

def set_max_selections(max_selections):
    """Salva número máximo de seleções na tabela config."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)", ('max_selections', str(max_selections)))
    conn.commit()
    conn.close()

def registrar_voto(user_id, escolhas_lista):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    escolhas_str = ", ".join(escolhas_lista)
    data_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # UPSERT: Insere ou Atualiza se o ID já existir (Permite mudar o voto)
    c.execute('''
        INSERT INTO votos (user_id, escolhas, timestamp) 
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            escolhas=excluded.escolhas,
            timestamp=excluded.timestamp
    ''', (user_id, escolhas_str, data_hora))
    
    conn.commit()
    conn.close()
    
    # Verifica se precisa fazer upload periódico para Dropbox
    verificar_upload_periodico()

def carregar_voto_existente(user_id):
    conn = sqlite3.connect(DB_FILE)
    row = conn.cursor().execute("SELECT escolhas FROM votos WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    if row:
        return row[0].split(", ")
    return []

def get_resultados_df():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM votos", conn)
    conn.close()
    return df

def extrair_nome_candidato(candidato_completo):
    """
    Extrai apenas o nome do candidato (antes do parêntese).
    
    Args:
        candidato_completo: String no formato "Nome (Instituição - Região)"
    
    Returns:
        str: Nome do candidato sem instituição/região
    """
    if '(' in candidato_completo:
        return candidato_completo.split('(')[0].strip()
    return candidato_completo.strip()

def gerar_csv_votos_formatado(df_votos):
    """
    Converte DataFrame de votos para formato com colunas por candidato.
    
    Args:
        df_votos: DataFrame com colunas user_id, escolhas, timestamp
    
    Returns:
        DataFrame: DataFrame formatado com colunas por candidato (1/0) e linha TOTAL
    """
    try:
        # Lê lista completa de candidatos primeiro (necessário mesmo sem votos)
        df_candidatos = ler_csv_candidatos()
        
        # Se não houver votos, retorna DataFrame vazio com apenas cabeçalho
        if df_votos.empty:
            # Cria lista formatada "Nome (Instituição - Região)" e extrai apenas nomes
            opcoes_completas = df_candidatos.apply(
                lambda x: f"{x['Nome']} ({x['Instituicao']} - {x['Regiao']})", 
                axis=1
            ).tolist()
            nomes_candidatos = [extrair_nome_candidato(opcao) for opcao in opcoes_completas]
            colunas = ['user_id', 'timestamp'] + sorted(nomes_candidatos) + ['Total_Votos_Eleitor']
            return pd.DataFrame(columns=colunas)
        
        # Cria lista formatada "Nome (Instituição - Região)" e extrai apenas nomes
        opcoes_completas = df_candidatos.apply(
            lambda x: f"{x['Nome']} ({x['Instituicao']} - {x['Regiao']})", 
            axis=1
        ).tolist()
        
        # Extrai apenas os nomes dos candidatos para usar como colunas
        nomes_candidatos = [extrair_nome_candidato(opcao) for opcao in opcoes_completas]
        
        # Cria dicionário para mapear nome completo -> nome simples
        mapeamento_nomes = {
            opcao_completa: nome_simples 
            for opcao_completa, nome_simples in zip(opcoes_completas, nomes_candidatos)
        }
        
        # Cria lista de dados para o novo DataFrame
        dados_formatados = []
        
        # Processa cada voto
        for _, row in df_votos.iterrows():
            user_id = row['user_id']
            timestamp = row['timestamp']
            escolhas_str = row['escolhas']
            
            # Separa as escolhas
            escolhas_lista = [e.strip() for e in escolhas_str.split(',')] if escolhas_str else []
            
            # Cria dicionário para esta linha
            linha = {
                'user_id': user_id,
                'timestamp': timestamp
            }
            
            # Inicializa todas as colunas de candidatos com 0
            for nome_candidato in nomes_candidatos:
                linha[nome_candidato] = 0
            
            # Marca 1 para os candidatos votados
            for escolha in escolhas_lista:
                escolha_limpa = escolha.strip()
                # Tenta encontrar o nome correspondente
                nome_correspondente = None
                for opcao_completa, nome_simples in mapeamento_nomes.items():
                    if escolha_limpa == opcao_completa:
                        nome_correspondente = nome_simples
                        break
                
                if nome_correspondente and nome_correspondente in linha:
                    linha[nome_correspondente] = 1
            
            # Calcula Total_Votos_Eleitor (soma de todas as colunas de candidatos)
            linha['Total_Votos_Eleitor'] = sum(
                linha[nome_candidato] for nome_candidato in nomes_candidatos
            )
            
            dados_formatados.append(linha)
        
        # Cria DataFrame
        df_formatado = pd.DataFrame(dados_formatados)
        
        # Se não houver dados, retorna DataFrame vazio com apenas cabeçalho
        if df_formatado.empty:
            colunas = ['user_id', 'timestamp'] + nomes_candidatos + ['Total_Votos_Eleitor']
            return pd.DataFrame(columns=colunas)
        
        # Reordena colunas: user_id, timestamp, candidatos (em ordem alfabética), Total_Votos_Eleitor
        colunas_ordenadas = ['user_id', 'timestamp'] + sorted(nomes_candidatos) + ['Total_Votos_Eleitor']
        # Garante que todas as colunas existem
        colunas_ordenadas = [col for col in colunas_ordenadas if col in df_formatado.columns]
        df_formatado = df_formatado[colunas_ordenadas]
        
        # Adiciona linha TOTAL
        linha_total = {
            'user_id': 'TOTAL',
            'timestamp': ''
        }
        
        # Soma de votos por candidato
        for nome_candidato in sorted(nomes_candidatos):
            if nome_candidato in df_formatado.columns:
                linha_total[nome_candidato] = df_formatado[nome_candidato].sum()
        
        # Total_Votos_Eleitor na linha TOTAL = soma total de todos os votos
        linha_total['Total_Votos_Eleitor'] = df_formatado['Total_Votos_Eleitor'].sum()
        
        # Adiciona linha TOTAL ao DataFrame
        df_total = pd.DataFrame([linha_total])
        df_formatado = pd.concat([df_formatado, df_total], ignore_index=True)
        
        return df_formatado
        
    except Exception as e:
        # Em caso de erro, retorna DataFrame original
        if 'st.error' in dir():
            st.error(f"Erro ao formatar CSV de votos: {e}")
        return df_votos

def fazer_backup_votacao():
    """Faz backup do CSV de votos e banco de dados com timestamp."""
    try:
        # Cria diretório de backups se não existir
        backup_dir = Path('backups')
        backup_dir.mkdir(exist_ok=True)
        
        # Gera timestamp no formato YYYYMMDD_HHMMSS
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Backup do CSV de votos (sempre salva, mesmo se vazio)
        df_votos = get_resultados_df()
        df_votos_formatado = gerar_csv_votos_formatado(df_votos)
        backup_csv_path = backup_dir / f'backup_votos_{timestamp}.csv'
        df_votos_formatado.to_csv(backup_csv_path, index=False, encoding='utf-8')
        
        # Backup do banco de dados
        if os.path.exists(DB_FILE):
            backup_db_path = backup_dir / f'backup_votos_{timestamp}.db'
            shutil.copy2(DB_FILE, backup_db_path)
        
        return timestamp
    except Exception as e:
        if 'st.error' in dir():
            st.error(f"Erro ao fazer backup: {e}")
        else:
            print(f"Erro ao fazer backup: {e}")
        return None

def resetar_votacao():
    """Reseta a votação: faz backup, deleta votos e reseta status."""
    try:
        # Faz backup antes de resetar
        timestamp = fazer_backup_votacao()
        if timestamp is None:
            return False
        
        # Deleta todos os votos
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("DELETE FROM votos")
        conn.commit()
        conn.close()
        
        # Reseta status para ABERTO
        set_voting_status('ABERTO')
        
        # Upload imediato para Dropbox após reset
        upload_db_to_dropbox()
        
        return True
    except Exception as e:
        st.error(f"Erro ao resetar votação: {e}")
        return False

# --- Funções de Integração com Dropbox ---
def init_dropbox_client():
    """
    Inicializa cliente do Dropbox usando Access Token.
    
    Returns:
        dropbox.Dropbox: Cliente do Dropbox ou None se não configurado
    """
    if not DROPBOX_AVAILABLE:
        return None
    
    if not DROPBOX_ACCESS_TOKEN:
        return None
    
    try:
        # Usa oauth2_access_token explicitamente para evitar tentativas de refresh
        client = dropbox.Dropbox(oauth2_access_token=DROPBOX_ACCESS_TOKEN)
        # Testa a conexão
        client.users_get_current_account()
        return client
    except AuthError as e:
        # Verifica se é erro de token expirado
        error_msg = str(e)
        if 'expired' in error_msg.lower() or 'expired_access_token' in error_msg:
            if 'st.error' in dir():
                st.error("⚠️ **Token do Dropbox expirado!** Gere um novo token no Dropbox Developer Console e atualize os secrets.")
            else:
                print("⚠️ Token do Dropbox expirado! Gere um novo token no Dropbox Developer Console.")
        else:
            if 'st.error' in dir():
                st.error("Erro de autenticação do Dropbox. Verifique o ACCESS_TOKEN.")
            else:
                print(f"Erro de autenticação do Dropbox: {e}")
        return None
    except Exception as e:
        if 'st.error' in dir():
            st.error(f"Erro ao inicializar Dropbox: {e}")
        else:
            print(f"Erro ao inicializar Dropbox: {e}")
        return None

def upload_db_to_dropbox():
    """
    Faz upload do banco de dados para Dropbox.
    Cria a pasta se não existir, atualiza arquivo existente ou cria novo.
    Salva timestamp do upload na tabela config.
    
    Returns:
        bool: True se upload foi bem-sucedido, False caso contrário
    """
    if not os.path.exists(DB_FILE):
        return False
    
    client = init_dropbox_client()
    if not client:
        return False
    
    try:
        # Lê o arquivo
        with open(DB_FILE, 'rb') as f:
            file_data = f.read()
        
        # Faz upload (sobrescreve se já existir)
        # Nota: A pasta deve existir no Dropbox ou o app precisa ter permissão para criar pastas
        client.files_upload(
            file_data,
            DROPBOX_FILE_PATH,
            mode=dropbox.files.WriteMode.overwrite
        )
        
        # Salva timestamp do upload na tabela config
        timestamp = datetime.now().isoformat()
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)",
            ('ultimo_upload_dropbox', timestamp)
        )
        conn.commit()
        conn.close()
        
        return True
    except AuthError as e:
        # Erro de autenticação (token expirado ou inválido)
        error_msg = str(e)
        if 'expired' in error_msg.lower() or 'expired_access_token' in error_msg:
            if 'st.error' in dir():
                st.error("⚠️ **Token do Dropbox expirado!** Gere um novo token no Dropbox Developer Console e atualize os secrets.")
            else:
                print("⚠️ Token do Dropbox expirado! Gere um novo token no Dropbox Developer Console.")
        else:
            if 'st.error' in dir():
                st.error(f"Erro de autenticação do Dropbox: {e}")
            else:
                print(f"Erro de autenticação do Dropbox: {e}")
        return False
    except ApiError as e:
        # Erro da API do Dropbox
        if 'st.error' in dir():
            st.error(f"Erro da API do Dropbox: {e}")
        else:
            print(f"Erro da API do Dropbox: {e}")
        return False
    except Exception as e:
        if 'st.error' in dir():
            st.error(f"Erro ao fazer upload para Dropbox: {e}")
        else:
            # Se não estiver no contexto do Streamlit, imprime o erro
            print(f"Erro ao fazer upload para Dropbox: {e}")
            import traceback
            traceback.print_exc()
        return False

def download_db_from_dropbox():
    """
    Baixa banco de dados do Dropbox.
    Substitui arquivo local se download for bem-sucedido.
    
    Returns:
        bool: True se download foi bem-sucedido, False caso contrário
    """
    client = init_dropbox_client()
    if not client:
        return False
    
    try:
        # Tenta baixar o arquivo
        metadata, response = client.files_download(DROPBOX_FILE_PATH)
        
        # Salva arquivo localmente
        with open(DB_FILE, 'wb') as f:
            f.write(response.content)
        
        return True
    except ApiError as e:
        if e.error.is_path() and e.error.get_path().is_not_found():
            # Arquivo não existe no Dropbox
            return False
        if 'st.error' in dir():
            st.error(f"Erro ao baixar do Dropbox: {e}")
        return False
    except Exception as e:
        if 'st.error' in dir():
            st.error(f"Erro ao baixar do Dropbox: {e}")
        return False

def verificar_e_restaurar_db():
    """
    Verifica se precisa restaurar banco do Dropbox na inicialização.
    Restaura se banco local estiver vazio ou mais antigo que o do Dropbox.
    """
    client = init_dropbox_client()
    if not client:
        return False
    
    try:
        # Verifica se banco local existe e tem dados
        banco_local_existe = os.path.exists(DB_FILE)
        banco_local_tem_dados = False
        timestamp_local = None
        
        if banco_local_existe:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM votos")
            count = c.fetchone()[0]
            banco_local_tem_dados = count > 0
            
            # Lê timestamp do último upload local
            c.execute("SELECT valor FROM config WHERE chave='ultimo_upload_dropbox'")
            result = c.fetchone()
            if result and result[0] and result[0].strip():
                try:
                    timestamp_local = datetime.fromisoformat(result[0])
                except (ValueError, TypeError):
                    timestamp_local = None
            conn.close()
        
        # Se banco local não tem dados, tenta restaurar do Dropbox
        if not banco_local_tem_dados:
            if download_db_from_dropbox():
                return True
        
        # Se banco local tem dados, compara com Dropbox
        # Verifica se arquivo existe no Dropbox e compara timestamps
        try:
            # Obtém metadata do arquivo no Dropbox
            metadata = client.files_get_metadata(DROPBOX_FILE_PATH)
            timestamp_dropbox = None
            
            # Tenta obter timestamp do arquivo no Dropbox
            if hasattr(metadata, 'server_modified'):
                # server_modified é datetime object no Dropbox SDK
                timestamp_dropbox = metadata.server_modified
            elif hasattr(metadata, 'client_modified'):
                timestamp_dropbox = metadata.client_modified
            
            # Se não tem timestamp local, sempre restaura do Dropbox para garantir sincronização
            if timestamp_local is None:
                if download_db_from_dropbox():
                    return True
            
            # Se ambos têm timestamps, compara
            if timestamp_dropbox and timestamp_local:
                # Converte timestamp_dropbox para timezone-aware se necessário
                if timestamp_dropbox.tzinfo is None:
                    # Assume UTC se não tiver timezone
                    timestamp_dropbox = timestamp_dropbox.replace(tzinfo=timezone.utc)
                
                if timestamp_local.tzinfo is None:
                    timestamp_local = timestamp_local.replace(tzinfo=timezone.utc)
                
                # Se Dropbox é mais recente, restaura
                if timestamp_dropbox > timestamp_local:
                    if download_db_from_dropbox():
                        return True
        except ApiError as e:
            # Se arquivo não existe no Dropbox, mantém local
            if not (e.error.is_path() and e.error.get_path().is_not_found()):
                # Outro erro, loga mas não interrompe
                if 'st.error' in dir():
                    st.error(f"Erro ao verificar arquivo no Dropbox: {e}")
        except Exception as e:
            # Erro ao comparar, se não tem timestamp local, tenta restaurar para garantir
            if timestamp_local is None:
                if download_db_from_dropbox():
                    return True
            # Se houver erro e já tem timestamp local, mantém local mas loga
            if 'st.error' in dir():
                st.error(f"Erro ao comparar timestamps: {e}")
        
        return False
    except Exception as e:
        if 'st.error' in dir():
            st.error(f"Erro ao verificar/restaurar banco: {e}")
        return False

def verificar_upload_periodico():
    """
    Verifica se precisa fazer upload periódico (a cada 15 minutos).
    Faz upload se passou o intervalo E há votos novos.
    
    Returns:
        bool: True se upload foi feito, False caso contrário
    """
    client = init_dropbox_client()
    if not client:
        return False
    
    try:
        # Verifica se há votos
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM votos")
        count_votos = c.fetchone()[0]
        
        # Lê timestamp do último upload
        c.execute("SELECT valor FROM config WHERE chave='ultimo_upload_dropbox'")
        result = c.fetchone()
        conn.close()
        
        # Se não há votos, não precisa fazer upload
        if count_votos == 0:
            return False
        
        # Se não há timestamp de upload anterior ou está vazio, faz upload
        if not result or not result[0] or result[0].strip() == '':
            return upload_db_to_dropbox()
        
        # Verifica se passou o intervalo
        try:
            ultimo_upload = datetime.fromisoformat(result[0])
            agora = datetime.now()
            intervalo = timedelta(minutes=UPLOAD_INTERVAL_MINUTES)
            
            if agora - ultimo_upload >= intervalo:
                return upload_db_to_dropbox()
        except (ValueError, TypeError):
            # Se houver erro ao parsear timestamp, faz upload
            return upload_db_to_dropbox()
        
        return False
    except Exception as e:
        # Se houver erro, não interrompe a aplicação
        return False

# --- Funções de Estilo e Logo ---
def encontrar_logo():
    """Encontra o arquivo de logo disponível."""
    possiveis_logos = [
        LOGO_PATH / 'ceie-logo-com-nome.png',  # Logo com nome (prioridade)
        LOGO_PATH / 'ceie-logo.png',  # Apenas logo
    ]
    
    for logo_path in possiveis_logos:
        if logo_path.exists():
            return logo_path
    return None

def extrair_cores_principais(imagem_path, num_cores=5):
    """Extrai as cores principais de uma imagem."""
    try:
        img = Image.open(imagem_path)
        # Redimensiona para processamento mais rápido
        img = img.resize((150, 150))
        # Converte para RGB se necessário
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Converte para array numpy
        img_array = np.array(img)
        # Redimensiona para lista de pixels
        pixels = img_array.reshape(-1, 3)
        
        # Remove pixels muito claros (branco/fundo) e muito escuros (preto)
        pixels_filtrados = [
            p for p in pixels 
            if not (np.all(p > 240) or np.all(p < 15))
        ]
        
        if not pixels_filtrados:
            pixels_filtrados = pixels
        
        # Agrupa cores similares e pega as mais frequentes
        cores_agrupadas = []
        for pixel in pixels_filtrados[:1000]:  # Amostra para performance
            # Arredonda para agrupar cores similares
            cor_arredondada = tuple((pixel // 20) * 20)
            cores_agrupadas.append(cor_arredondada)
        
        contador = Counter(cores_agrupadas)
        cores_principais = contador.most_common(num_cores)
        
        # Converte para formato hex
        cores_hex = []
        for cor, _ in cores_principais:
            hex_color = '#{:02x}{:02x}{:02x}'.format(
                int(cor[0]), int(cor[1]), int(cor[2])
            )
            cores_hex.append(hex_color)
        
        return cores_hex
    except Exception as e:
        # Retorna cores padrão em caso de erro
        return ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']

def hex_to_rgba(hex_color, alpha=1.0):
    """Converte cor hex para rgba."""
    hex_color = hex_color.lstrip('#')
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"

def identificar_cor_azul(cores):
    """Identifica a cor mais azul entre as cores extraídas."""
    if not cores:
        return '#1f77b4'
    
    melhor_azul = None
    maior_score_azul = -1
    
    for cor in cores:
        hex_color = cor.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        
        # Calcula score de "azulidade" (B deve ser maior que R e G)
        if b > r and b > g:
            score_azul = b - max(r, g)
            if score_azul > maior_score_azul:
                maior_score_azul = score_azul
                melhor_azul = cor
    
    # Se não encontrou uma cor claramente azul, retorna a primeira cor
    # ou uma cor azul padrão
    if melhor_azul is None:
        # Tenta encontrar qualquer cor com B > 100 (azul médio/forte)
        for cor in cores:
            hex_color = cor.lstrip('#')
            b = int(hex_color[4:6], 16)
            if b > 100:
                return cor
        return '#1f77b4'  # Azul padrão
    
    return melhor_azul

def aplicar_estilo_ceie(cores):
    """Aplica CSS customizado com as cores do logo."""
    if not cores:
        cores = ['#1f77b4', '#ff7f0e']
    
    cor_primaria = cores[0] if len(cores) > 0 else '#1f77b4'
    cor_secundaria = cores[1] if len(cores) > 1 else '#ff7f0e'
    cor_terciaria = cores[2] if len(cores) > 2 else cores[0]
    
    # Converte para rgba para transparências
    cor_primaria_rgba_light = hex_to_rgba(cor_primaria, 0.15)
    cor_secundaria_rgba_light = hex_to_rgba(cor_secundaria, 0.15)
    cor_primaria_rgba_border = hex_to_rgba(cor_primaria, 0.3)
    
    css = f"""
    <style>
        /* Cores principais */
        :root {{
            --cor-primaria: {cor_primaria};
            --cor-secundaria: {cor_secundaria};
            --cor-terciaria: {cor_terciaria};
        }}
        
        /* Estilo do header */
        .main .block-container {{
            padding-top: 2rem;
        }}
        
        /* Botões primários */
        .stButton > button {{
            background-color: {cor_primaria};
            color: white;
            border: none;
            border-radius: 8px;
            padding: 0.5rem 1rem;
            font-weight: 600;
            transition: all 0.3s;
        }}
        
        .stButton > button:hover {{
            background-color: {cor_secundaria};
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        }}
        
        .stButton > button:disabled {{
            background-color: #cccccc;
            color: #666666;
            cursor: not-allowed;
        }}
        
        /* Títulos */
        h1 {{
            color: {cor_primaria};
            border-bottom: 3px solid {cor_secundaria};
            padding-bottom: 0.5rem;
        }}
        
        h2, h3 {{
            color: {cor_primaria};
        }}
        
        /* Sidebar */
        .css-1d391kg {{
            background-color: #f8f9fa;
        }}
        
        /* Checkboxes */
        .stCheckbox > label {{
            font-size: 1rem;
            padding: 0.5rem;
            border-radius: 4px;
            transition: background-color 0.2s;
        }}
        
        .stCheckbox > label:hover {{
            background-color: rgba(31, 119, 180, 0.1);
        }}
        
        /* Mensagens de info */
        .stInfo {{
            background-color: {cor_primaria_rgba_light};
            border-left: 4px solid {cor_primaria};
        }}
        
        /* Mensagens de sucesso */
        .stSuccess {{
            background-color: rgba(44, 160, 44, 0.1);
            border-left: 4px solid #2ca02c;
        }}
        
        /* Mensagens de erro */
        .stError {{
            background-color: rgba(214, 39, 40, 0.1);
            border-left: 4px solid #d62728;
        }}
        
        /* Logo container */
        .logo-container {{
            text-align: center;
            margin-bottom: 2rem;
            padding: 0;
        }}
        
        .logo-container img {{
            max-width: 300px;
            height: auto;
            margin: 0 auto;
        }}
        
        .logo-container h1 {{
            margin-top: 0;
            margin-bottom: 1rem;
            font-size: 2rem;
            font-weight: 600;
        }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

def exibir_logo(mostrar_titulo=False, cor_primaria='#1f77b4'):
    """Exibe o logo da CEIE no topo da página."""
    logo_path = encontrar_logo()
    if logo_path:
        try:
            img = Image.open(logo_path)
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.markdown('<div class="logo-container">', unsafe_allow_html=True)
                if mostrar_titulo:
                    titulo = get_titulo_votacao()
                    st.markdown(f'<h1 style="text-align: center; margin-bottom: 1rem; color: {cor_primaria};">{titulo}</h1>', unsafe_allow_html=True)
                st.image(img, width='stretch')
                st.markdown('</div>', unsafe_allow_html=True)
            return logo_path
        except Exception as e:
            st.warning(f"Erro ao carregar logo: {e}")
            return None
    return None

# --- Funções de Validação de CSVs ---
def validar_csv_eleitores(df):
    """Valida se o DataFrame de eleitores tem as colunas obrigatórias."""
    colunas_obrigatorias = ['Email', 'Nome', 'id_sbc']
    colunas_presentes = df.columns.tolist()
    
    for coluna in colunas_obrigatorias:
        if coluna not in colunas_presentes:
            return False, f"Coluna obrigatória '{coluna}' não encontrada no CSV de eleitores."
    
    # Valida se há dados
    if df.empty:
        return False, "CSV de eleitores está vazio."
    
    return True, None

def validar_csv_candidatos(df):
    """Valida se o DataFrame de candidatos tem as colunas obrigatórias."""
    colunas_obrigatorias = ['Nome', 'Instituicao', 'Regiao']
    colunas_presentes = df.columns.tolist()
    
    for coluna in colunas_obrigatorias:
        if coluna not in colunas_presentes:
            return False, f"Coluna obrigatória '{coluna}' não encontrada no CSV de candidatos."
    
    # Valida se há dados
    if df.empty:
        return False, "CSV de candidatos está vazio."
    
    return True, None

# --- Funções de Validação ---
def validar_usuario(email, senha=None):
    """
    Valida usuário (eleitor ou admin).
    
    Args:
        email: Email do usuário
        senha: Senha (obrigatória para admin e eleitores)
               - Admin: senha configurada
               - Eleitores: número de sócio SBC (id_sbc)
    
    Returns:
        tuple: (valido, nome, is_admin)
    """
    if not email:
        return False, None, False
    
    email = email.strip().lower()
    senha = senha.strip() if senha and senha.strip() else ""
    
    # Verifica se é admin
    if email == EMAIL_ADMIN.lower():
        if senha == SENHA_ADMIN:
            return True, "Administrador", True
        return False, None, False
    
    # Verifica se é eleitor (precisa de senha = id_sbc)
    try:
        df = ler_csv_eleitores()
        df['Email'] = df['Email'].astype(str).str.strip().str.lower()
        
        usuario = df[df['Email'] == email]
        if not usuario.empty:
            # Verifica se a senha (id_sbc) foi fornecida e está correta
            if not senha:
                return False, None, False
            
            # Converte id_sbc para string para comparação
            id_sbc_cadastrado = str(int(usuario.iloc[0]['id_sbc']))
            if senha.strip() == id_sbc_cadastrado:
                return True, usuario.iloc[0]['Nome'], False
            return False, None, False
        return False, None, False
    except FileNotFoundError:
        st.error(f"Erro: Arquivo '{ARQUIVO_ELEITORES}' não encontrado.")
        return False, None, False
    except (KeyError, ValueError) as e:
        st.error(f"Erro ao validar eleitor: {e}")
        return False, None, False

def validar_eleitor(identificador):
    """Mantida para compatibilidade."""
    valido, nome, _ = validar_usuario(identificador)
    return valido, nome

# --- Interface do Usuário (Front-end) ---
def main():
    init_db()
    
    # Verifica e restaura banco do Google Drive se necessário
    verificar_e_restaurar_db()
    
    # Extrai cores do logo para aplicar estilo (sem exibir o logo ainda)
    logo_path = encontrar_logo()
    if logo_path:
        cores = extrair_cores_principais(logo_path)
        aplicar_estilo_ceie(cores)
        # Identifica a cor azul do logo para usar no título
        cor_azul_logo = identificar_cor_azul(cores)
        cor_primaria = cores[0] if len(cores) > 0 else '#1f77b4'
    else:
        # Aplica estilo padrão se não houver logo
        aplicar_estilo_ceie(['#1f77b4', '#ff7f0e'])
        cor_azul_logo = '#1f77b4'
        cor_primaria = '#1f77b4'
    

    # Lógica Principal
    if 'usuario_validado' not in st.session_state:
        st.session_state.usuario_validado = None
    if 'admin_logado' not in st.session_state:
        st.session_state.admin_logado = False

    status_votacao = get_voting_status()

    if status_votacao == 'FECHADO' and not st.session_state.usuario_validado:
        st.warning("A votação está encerrada.")
        return

    # Tela de Login
    if st.session_state.usuario_validado is None:
        # Exibe logo apenas na tela de login com título dentro do retângulo
        if logo_path:
            exibir_logo(mostrar_titulo=True, cor_primaria=cor_azul_logo)
        
        st.subheader("Identificação")
        
        with st.form("form_login"):
            email_input = st.text_input("Digite seu E-mail:")
            senha_input = st.text_input("Digite sua Senha:", type="password", help="Para eleitores: número de sócio SBC (id_sbc). Para administrador: senha configurada.")
            submitted = st.form_submit_button("Acessar", type="primary")
            
            if submitted:
                valido, nome, is_admin = validar_usuario(email_input, senha_input)
                if valido:
                    st.session_state.usuario_validado = email_input
                    st.session_state.nome_usuario = nome
                    st.session_state.admin_logado = is_admin
                    st.rerun()
                else:
                    if email_input and email_input.strip().lower() == EMAIL_ADMIN.lower():
                        st.error("Senha incorreta para administrador.")
                    else:
                        st.error("E-mail não encontrado ou senha (id_sbc) incorreta.")

    # Tela de Votação (apenas para eleitores, não para admin)
    else:
        # Se for admin, mostra área administrativa na área principal
        if st.session_state.admin_logado:
            st.title("🔐 Área Administrativa")
            st.success("👤 Logado como **Administrador**")
            st.markdown("---")
            
            # Controle de Status
            col1, col2, col3 = st.columns([1, 1, 1])
            status_atual = get_voting_status()
            
            with col1:
                st.metric("Status da Votação", status_atual)
            
            with col2:
                if status_atual == 'ABERTO':
                    if st.button("🔒 Encerrar Votação", type="primary"):
                        set_voting_status('FECHADO')
                        st.rerun()
                else:
                    if st.button("🔓 Reabrir Votação", type="primary"):
                        set_voting_status('ABERTO')
                        st.rerun()
            
            with col3:
                if st.button("🚪 Sair do Admin"):
                    st.session_state.admin_logado = False
                    st.session_state.usuario_validado = None
                    st.session_state.nome_usuario = None
                    st.rerun()
            
            st.markdown("---")
            
            # Auditoria e Download
            st.subheader("📊 Auditoria em Tempo Real")
            df_votos = get_resultados_df()
            total_votos = len(df_votos)
            st.write(f"**Total de votantes:** {total_votos}")
            
            if total_votos > 0:
                # Processamento para contagem (explode multiselect)
                todas_escolhas = []
                for voto in df_votos['escolhas']:
                    todas_escolhas.extend(voto.split(", "))
                
                contagem = pd.Series(todas_escolhas).value_counts()
                
                st.markdown("### 📈 Resultados por Candidato")
                st.bar_chart(contagem)
                
                # Lista de candidatos ordenada por votos (decrescente)
                st.markdown("### 📊 Ranking de Candidatos")
                
                # Cria DataFrame com ranking
                df_ranking = pd.DataFrame({
                    'Candidato': contagem.index,
                    'Votos': contagem.values
                })
                df_ranking = df_ranking.sort_values('Votos', ascending=False)
                df_ranking.reset_index(drop=True, inplace=True)
                
                # Exibe a lista formatada
                for posicao, (_, row) in enumerate(df_ranking.iterrows(), start=1):
                    st.markdown(f"{posicao}º **{row['Candidato']}** - **{row['Votos']}** voto(s)")
                
                # Download dos dados
                col_dl1, col_dl2 = st.columns(2)
                with col_dl1:
                    df_votos_formatado = gerar_csv_votos_formatado(df_votos)
                    st.download_button(
                        label="📥 Baixar CSV de Votos",
                        data=df_votos_formatado.to_csv(index=False).encode('utf-8'),
                        file_name='auditoria_votos_ceie.csv',
                        mime='text/csv',
                    )
                
                with col_dl2:
                    with open(DB_FILE, "rb") as fp:
                        st.download_button(
                            label="💾 Baixar Backup Banco (SQLite)",
                            data=fp,
                            file_name="backup_votos.db",
                            mime="application/octet-stream",
                        )
            else:
                st.info("Ainda não há votos registrados.")
            
            st.markdown("---")
            
            # Seção Nova Votação
            st.subheader("🔄 Nova Votação")
            st.info("⚠️ **Atenção:** Ao iniciar uma nova votação, será feito backup automático dos dados atuais (CSV de votos e banco de dados) com data/hora. Todos os votos atuais serão deletados.")
            
            # Configurações da votação
            st.markdown("#### ⚙️ Configurações da Votação")
            titulo_atual = get_titulo_votacao()
            max_selections_atual = get_max_selections()
            
            novo_titulo = st.text_input(
                "Título da Votação:",
                value=titulo_atual,
                help="Título que será exibido na tela de login e no navegador",
                key="input_titulo_votacao"
            )
            
            novo_max_selections = st.number_input(
                "Número Máximo de Votos:",
                min_value=1,
                max_value=10,
                value=max_selections_atual,
                help="Número máximo de candidatos que cada eleitor pode selecionar",
                key="input_max_selections"
            )
            
            st.markdown("---")
            
            # Opções: Upload de arquivos ou colar texto
            opcao_upload = st.radio(
                "Como deseja fornecer os novos CSVs?",
                ["📤 Upload de arquivos", "📝 Colar conteúdo"],
                horizontal=True
            )
            
            novo_eleitores_df = None
            novo_candidatos_df = None
            
            if opcao_upload == "📤 Upload de arquivos":
                st.markdown("#### Upload de Arquivos CSV")
                uploaded_eleitores = st.file_uploader(
                    "Upload eleitores.csv",
                    type=['csv'],
                    key="upload_eleitores"
                )
                uploaded_candidatos = st.file_uploader(
                    "Upload candidatos.csv",
                    type=['csv'],
                    key="upload_candidatos"
                )
                
                if uploaded_eleitores is not None:
                    try:
                        novo_eleitores_df = pd.read_csv(uploaded_eleitores)
                        st.success(f"✅ CSV de eleitores carregado: {len(novo_eleitores_df)} eleitores")
                    except Exception as e:
                        st.error(f"Erro ao ler CSV de eleitores: {e}")
                
                if uploaded_candidatos is not None:
                    try:
                        novo_candidatos_df = pd.read_csv(uploaded_candidatos)
                        st.success(f"✅ CSV de candidatos carregado: {len(novo_candidatos_df)} candidatos")
                    except Exception as e:
                        st.error(f"Erro ao ler CSV de candidatos: {e}")
            
            else:  # Colar conteúdo
                st.markdown("#### Colar Conteúdo dos CSVs")
                texto_eleitores = st.text_area(
                    "Cole o conteúdo do CSV de eleitores (Email,Nome,id_sbc):",
                    height=150,
                    key="texto_eleitores"
                )
                texto_candidatos = st.text_area(
                    "Cole o conteúdo do CSV de candidatos (Nome,Instituicao,Regiao):",
                    height=150,
                    key="texto_candidatos"
                )
                
                if texto_eleitores.strip():
                    try:
                        novo_eleitores_df = pd.read_csv(StringIO(texto_eleitores))
                        st.success(f"✅ CSV de eleitores carregado: {len(novo_eleitores_df)} eleitores")
                    except Exception as e:
                        st.error(f"Erro ao processar CSV de eleitores: {e}")
                
                if texto_candidatos.strip():
                    try:
                        novo_candidatos_df = pd.read_csv(StringIO(texto_candidatos))
                        st.success(f"✅ CSV de candidatos carregado: {len(novo_candidatos_df)} candidatos")
                    except Exception as e:
                        st.error(f"Erro ao processar CSV de candidatos: {e}")
            
            # Verifica se ambos os CSVs foram fornecidos para habilitar/desabilitar botão
            csvs_fornecidos = (novo_eleitores_df is not None and novo_candidatos_df is not None)
            
            # Botão para iniciar nova votação (desabilitado se não houver CSVs)
            if st.button(
                "🔄 Iniciar Nova Votação", 
                type="primary",
                disabled=not csvs_fornecidos
            ):
                # Valida os CSVs
                valido_eleitores, erro_eleitores = validar_csv_eleitores(novo_eleitores_df)
                valido_candidatos, erro_candidatos = validar_csv_candidatos(novo_candidatos_df)
                
                if not valido_eleitores:
                    st.error(f"Erro na validação de eleitores: {erro_eleitores}")
                elif not valido_candidatos:
                    st.error(f"Erro na validação de candidatos: {erro_candidatos}")
                else:
                    # Salva configurações antes de resetar
                    if novo_titulo and novo_titulo.strip():
                        set_titulo_votacao(novo_titulo.strip())
                    set_max_selections(int(novo_max_selections))
                    
                    # Faz reset da votação (backup + deleta votos)
                    if resetar_votacao():
                        # Salva novos CSVs
                        try:
                            # Salva como arquivos locais
                            novo_eleitores_df.to_csv(ARQUIVO_ELEITORES, index=False, encoding='utf-8')
                            novo_candidatos_df.to_csv(ARQUIVO_CANDIDATOS, index=False, encoding='utf-8')
                            
                            # Limpa estados de sessão relacionados a votos
                            keys_to_delete = [key for key in st.session_state.keys() if 'checkbox' in key or 'voto' in key]
                            for key in keys_to_delete:
                                del st.session_state[key]
                            
                            # Marca que nova votação foi iniciada com sucesso
                            st.session_state.nova_votacao_iniciada = True
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao salvar novos CSVs: {e}")
                    else:
                        st.error("Erro ao resetar votação. Verifique os logs.")
            
            # Exibe mensagem de confirmação se nova votação foi iniciada
            if st.session_state.get('nova_votacao_iniciada', False):
                st.success("✅ **Nova votação iniciada com sucesso!** Backup automático realizado.")
                st.balloons()
                # Remove a flag após exibir a mensagem (para não aparecer em reruns futuros)
                del st.session_state.nova_votacao_iniciada
            
            # Exibe aviso se CSVs não foram fornecidos
            if not csvs_fornecidos:
                st.warning("⚠️ Por favor, forneça ambos os CSVs (eleitores e candidatos) antes de iniciar uma nova votação.")
            
            return
        
        st.write(f"Olá, **{st.session_state.nome_usuario}**!")
        
        if status_votacao == 'FECHADO':
            st.info("A votação foi encerrada. Obrigado pela participação.")
            voto_atual = carregar_voto_existente(st.session_state.usuario_validado)
            if voto_atual:
                st.success(f"Seus votos computados: {', '.join(voto_atual)}")
            return

        try:
            df_candidatos = ler_csv_candidatos()
            # Cria lista formatada "Nome - Instituição" e ordena alfabeticamente
            opcoes = df_candidatos.apply(lambda x: f"{x['Nome']} ({x['Instituicao']} - {x['Regiao']})", axis=1).tolist()
            opcoes.sort()  # Ordena alfabeticamente
        except FileNotFoundError:
            st.error("Arquivo de candidatos não encontrado.")
            return

        # Verifica se o voto foi confirmado
        if 'voto_confirmado' in st.session_state and st.session_state.voto_confirmado:
            # Tela de confirmação
            st.balloons()
            st.success("✅ Voto registrado com sucesso!")
            st.markdown("---")
            
            st.markdown("### 📋 Resumo do seu voto:")
            st.markdown(f"**Eleitor:** {st.session_state.nome_usuario}")
            st.markdown(f"**E-mail:** {st.session_state.usuario_validado}")
            st.markdown("**Candidatos selecionados:**")
            
            # Lista os candidatos votados
            candidatos_votados = st.session_state.get('candidatos_votados', [])
            for i, candidato in enumerate(candidatos_votados, 1):
                st.markdown(f"{i}. {candidato}")
            
            st.markdown("---")
            st.info("🔒 Por segurança, você será desconectado.")
            
            # Faz logout quando o usuário clicar no botão
            col1, col2, col3 = st.columns([1, 1, 1])
            with col2:
                if st.button("Sair", type="primary", key="btn_sair_confirmacao"):
                    # Salva o email antes de limpar
                    email_antigo = st.session_state.usuario_validado
                    # Limpa os checkboxes
                    checkbox_key = f"checkboxes_{email_antigo}"
                    if checkbox_key in st.session_state:
                        del st.session_state[checkbox_key]
                    # Limpa flags de confirmação
                    if 'voto_confirmado' in st.session_state:
                        del st.session_state.voto_confirmado
                    if 'candidatos_votados' in st.session_state:
                        del st.session_state.candidatos_votados
                    # Faz logout
                    st.session_state.usuario_validado = None
                    st.session_state.nome_usuario = None
                    st.rerun()
        else:
            # Tela de votação normal
            # Carrega voto anterior se existir (para permitir edição)
            escolhas_anteriores = carregar_voto_existente(st.session_state.usuario_validado)
            
            # Inicializa estado dos checkboxes se não existir
            checkbox_key = f"checkboxes_{st.session_state.usuario_validado}"
            if checkbox_key not in st.session_state:
                st.session_state[checkbox_key] = {
                    opcao: opcao in escolhas_anteriores 
                    for opcao in opcoes
                }
            
            max_selections = get_max_selections()
            st.write(f"Selecione até **{max_selections}** candidatos:")
            st.write("")  # Espaço em branco
            
            # Cria checkboxes individuais (fora do form para validação em tempo real)
            escolhas = []
            checkbox_states = {}
            
            for opcao in opcoes:
                # Usa o estado salvo como valor padrão
                default_value = st.session_state[checkbox_key].get(opcao, False)
                checkbox_value = st.checkbox(
                    opcao,
                    value=default_value,
                    key=f"checkbox_{opcao}_{st.session_state.usuario_validado}"
                )
                checkbox_states[opcao] = checkbox_value
                if checkbox_value:
                    escolhas.append(opcao)
            
            # Atualiza o estado dos checkboxes
            st.session_state[checkbox_key] = checkbox_states
            
            # Mostra contador de seleções em tempo real
            num_selecionados = len(escolhas)
            st.write("")  # Espaço em branco
            
            if num_selecionados > max_selections:
                st.error(
                    f"⚠️ Você selecionou **{num_selecionados}** candidatos, "
                    f"mas o máximo permitido é **{max_selections}**. "
                    "Por favor, desmarque algumas opções."
                )
            else:
                st.info(f"📊 Selecionados: **{num_selecionados}/{max_selections}**")
            
            st.write("")  # Espaço em branco
            
            # Determina se o botão deve estar desabilitado
            botao_desabilitado = (num_selecionados == 0 or num_selecionados > max_selections)
            
            # Botão de confirmação (sem form - apenas clique)
            if st.button(
                "✅ Confirmar Voto", 
                type="primary",
                disabled=botao_desabilitado
            ):
                if len(escolhas) == 0:
                    st.warning("Por favor, selecione ao menos um candidato.")
                elif len(escolhas) > max_selections:
                    st.error(
                        f"Você selecionou {len(escolhas)} candidatos, "
                        f"mas o máximo permitido é {max_selections}. "
                        "Por favor, desmarque algumas opções e tente novamente."
                    )
                else:
                    registrar_voto(st.session_state.usuario_validado, escolhas)
                    # Marca voto como confirmado e salva candidatos
                    st.session_state.voto_confirmado = True
                    st.session_state.candidatos_votados = escolhas
                    st.rerun()
            
            # Mostra aviso se já votou anteriormente
            if escolhas_anteriores:
                st.info("ℹ️ Você já votou anteriormente. Ao confirmar novamente, seu voto antigo será substituído.")

if __name__ == "__main__":
    main()