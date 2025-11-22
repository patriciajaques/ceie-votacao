# 🗳️ Sistema de Votação CEIE

Sistema de votação eletrônica desenvolvido com Streamlit para a Comissão Especial de Informática na Educação (CEIE).

## 📋 Funcionalidades

- ✅ Login unificado para eleitores e administradores
- ✅ Validação de eleitores por email e número de sócio SBC (id_sbc)
- ✅ Seleção de candidatos com checkboxes (até N candidatos configurável)
- ✅ Validação em tempo real de seleções
- ✅ Área administrativa com resultados em tempo real
- ✅ Download de auditoria (CSV e backup SQLite)
- ✅ Interface personalizada com cores do logo CEIE

## 🚀 Instalação Local

### Pré-requisitos

- Python 3.11+
- Conda (recomendado)

### Passos

1. Clone o repositório:
```bash
git clone https://github.com/patriciajaques/ceie-votacao.git
cd ceie-votacao
```

2. Ative o ambiente Conda:
```bash
conda activate ceie-workshops
```

3. Instale as dependências:
```bash
pip install -r requirements.txt
```

4. Configure os secrets (crie `.streamlit/secrets.toml`):
```toml
EMAIL_ADMIN = "admin"
PASSWORD_ADMIN = "sua_senha_aqui"
MAX_SELECTIONS = 3
```

5. Prepare os arquivos CSV:
   - `eleitores.csv` - Lista de eleitores (Email, Nome, id_sbc)
   - `candidatos.csv` - Lista de candidatos (Nome, Instituicao, Regiao)

6. Execute a aplicação:
```bash
streamlit run src/app.py
```

## ☁️ Deploy no Streamlit Cloud

Consulte o arquivo [DEPLOY.md](DEPLOY.md) para instruções detalhadas de deploy.

**Resumo rápido:**
1. Faça push do código para um repositório Git
2. Conecte o repositório no [Streamlit Cloud](https://share.streamlit.io/)
3. Configure os Secrets com os dados dos CSVs
4. Faça deploy!

## 🔒 Segurança

- Arquivos sensíveis (CSVs, banco de dados) estão no `.gitignore`
- Secrets não são versionados
- Senhas são obrigatórias para todos os usuários
- Banco de dados SQLite para persistência

## 📁 Estrutura do Projeto

```
ceie_votacao/
├── src/
│   └── app.py              # Aplicação principal
├── logo/                    # Logos da CEIE
├── .streamlit/
│   └── secrets.toml        # Configurações (não versionado)
├── requirements.txt         # Dependências Python
├── .gitignore              # Arquivos ignorados pelo Git
├── DEPLOY.md               # Guia de deploy
└── README.md               # Este arquivo
```

## 📝 Notas

- O banco de dados `votos.db` é criado automaticamente na primeira execução
- Os CSVs podem ser configurados via arquivos locais ou via Secrets (Streamlit Cloud)
- O número máximo de seleções é configurável via `MAX_SELECTIONS` nos secrets

## 👥 Desenvolvido para

Comissão Especial de Informática na Educação (CEIE)

## 📄 Licença

Este projeto está licenciado sob a [Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License](LICENSE).
