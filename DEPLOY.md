# Guia de Deploy - Streamlit Community Cloud

Este guia explica como fazer o deploy da aplicação de votação CEIE no Streamlit Community Cloud, protegendo arquivos sensíveis.

## 📋 Pré-requisitos

1. Conta no [Streamlit Community Cloud](https://share.streamlit.io/)
2. Repositório Git (GitHub, GitLab ou Bitbucket)
3. Arquivos CSV e banco de dados preparados

## 🔒 Proteção de Arquivos Sensíveis

### Arquivos que NÃO devem ser versionados:

- `eleitores.csv` - Lista de eleitores com emails e id_sbc
- `candidatos.csv` - Lista de candidatos
- `votos.db` - Banco de dados SQLite
- `.streamlit/secrets.toml` - Credenciais de admin

Estes arquivos estão no `.gitignore` e devem ser configurados via Secrets no Streamlit Cloud.

## 🚀 Passo a Passo do Deploy

### 1. Preparar o Repositório

```bash
# Certifique-se de que os arquivos sensíveis estão no .gitignore
git add .gitignore
git commit -m "chore: add gitignore for sensitive files"
```

### 2. Estrutura de Arquivos no Repositório

O repositório deve conter:
```
ceie_votacao/
├── src/
│   └── app.py
├── logo/
│   ├── ceie-logo-com-nome.png
│   └── ceie-logo.png
├── requirements.txt
├── .gitignore
└── README.md (opcional)
```

**NÃO inclua:**
- `eleitores.csv`
- `candidatos.csv`
- `votos.db`
- `.streamlit/secrets.toml`

### 3. Configurar Secrets no Streamlit Cloud

1. Acesse [share.streamlit.io](https://share.streamlit.io/)
2. Faça login e clique em "New app"
3. Conecte seu repositório
4. Configure o app:
   - **Main file path**: `src/app.py`
   - **Python version**: 3.11 (ou a versão que você está usando)

5. Antes de fazer deploy, configure os Secrets:
   - Clique em "Advanced settings" → "Secrets"
   - Adicione os seguintes secrets:

```toml
EMAIL_ADMIN = "admin"
PASSWORD_ADMIN = "sua_senha_admin_aqui"
MAX_SELECTIONS = 3

# Dropbox Configuration (opcional - para backup automático)
[DROPBOX]
ACCESS_TOKEN = "seu_token_dropbox_aqui"
FOLDER = "/CEIE_Votacao_Backups"  # Opcional: pasta onde o backup será salvo
```

### 4. Configurar Arquivos CSV via Secrets

Como os CSVs não podem ser versionados, você deve configurá-los via Secrets.

#### Gerar Secrets a partir dos CSVs locais:

Execute o script auxiliar (opcional):
```bash
python gerar_secrets.py
```

Ou configure manualmente nos Secrets do Streamlit Cloud:

```toml
EMAIL_ADMIN = "admin"
PASSWORD_ADMIN = "sua_senha_admin_aqui"
MAX_SELECTIONS = 3

# CSV de Eleitores (copie o conteúdo completo do arquivo eleitores.csv)
ELEITORES_CSV = """
Email,Nome,id_sbc
user1@email.com,Ana Silva,1001
user2@email.com,Bruno Oliveira,1002
...
"""

# CSV de Candidatos (copie o conteúdo completo do arquivo candidatos.csv)
CANDIDATOS_CSV = """
Nome,Instituicao,Regiao
Prof. Dr. Carlos Mendes,Universidade Federal do Rio de Janeiro,Sudeste
...
"""

# Dropbox Configuration (opcional - para backup automático)
# Veja DROPBOX_SETUP.md para instruções de como obter o ACCESS_TOKEN
[DROPBOX]
ACCESS_TOKEN = "seu_token_dropbox_aqui"
FOLDER = "/CEIE_Votacao_Backups"  # Opcional: pasta onde o backup será salvo
```

**Nota:** O código já está preparado para ler dos secrets quando os arquivos não existirem localmente.

### 5. Verificar Configuração do Código

O código já está preparado para:
1. ✅ Ler CSVs dos secrets se os arquivos não existirem localmente
2. ✅ Criar o banco de dados automaticamente
3. ✅ Usar secrets para configurações (EMAIL_ADMIN, PASSWORD_ADMIN, MAX_SELECTIONS)

### 6. Fazer Deploy

1. Clique em "Deploy!"
2. Aguarde o build completar
3. Acesse a URL fornecida

## 🔐 Segurança Adicional

### Recomendações:

1. **Nunca commite** arquivos com dados sensíveis
2. Use senhas fortes para o admin
3. Considere usar variáveis de ambiente para produção
4. Monitore os logs de acesso
5. Faça backup regular do banco de dados

## 📝 Notas Importantes

- O banco de dados `votos.db` será criado automaticamente na primeira execução
- Os CSVs devem ser configurados via Secrets ou carregados de outra fonte segura
- **Backup Automático**: Se configurar Dropbox, o banco será automaticamente restaurado se a aplicação reiniciar
- O Streamlit Cloud reinicia a aplicação após inatividade, mas com Dropbox configurado, os dados são preservados
- Consulte `DROPBOX_SETUP.md` para instruções detalhadas sobre configuração do Dropbox

## 🆘 Troubleshooting

- **Erro ao ler CSV**: Verifique se os secrets estão configurados corretamente
- **Banco de dados não persiste**: O Streamlit Cloud mantém o banco entre sessões, mas pode ser resetado
- **Secrets não funcionam**: Verifique a sintaxe TOML e se os secrets estão no formato correto
