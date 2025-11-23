# Configuração do Dropbox para Backup Automático

## Como obter o Access Token do Dropbox

### Passo 1: Criar App no Dropbox

1. Acesse: https://www.dropbox.com/developers/apps
2. Clique em **"Create app"**
3. Configure:
   - **Choose an API**: Selecione **"Scoped access"**
   - **Choose the type of access you need**: Selecione **"Full Dropbox"** (acesso completo)
   - **Name your app**: Digite um nome (ex: "CEIE Votacao Backup")
   - **App folder name**: Pode deixar em branco ou usar "CEIE Votacao"
4. Clique em **"Create app"**

### Passo 2: Habilitar Permissões Necessárias

1. Na página do app criado, vá para a aba **"Permissions"**
2. Habilite as seguintes permissões (scopes):
   - ✅ **files.content.write** - Para fazer upload de arquivos
   - ✅ **files.content.read** - Para fazer download de arquivos
   - ✅ **files.metadata.read** - Para verificar se arquivos/pastas existem (opcional, mas recomendado)
3. Clique em **"Submit"** para salvar as permissões

**Importante:** Sem essas permissões, o upload/download não funcionará!

### Passo 3: Gerar Access Token

1. Na página do app criado, vá para a aba **"Settings"**
2. Role até a seção **"OAuth 2"**
3. Em **"Generated access token"**, clique em **"Generate"**
4. **Copie o token gerado** (ele só aparece uma vez!)

**⚠️ Importante sobre Expiração de Tokens:**
- Tokens gerados diretamente no console podem expirar após algum tempo
- Se o token expirar, você verá uma mensagem de erro no app
- Para gerar um novo token: volte ao Passo 3 e clique em **"Regenerate"** ou **"Generate"**
- Atualize o token em dois lugares:
  1. Arquivo local: `.streamlit/secrets.toml`
  2. Streamlit Cloud: Settings → Secrets

**💡 Dica:** Para evitar expiração frequente, considere implementar refresh tokens (requer OAuth flow completo).

### Passo 4: Criar Pasta no Dropbox (Opcional)

A pasta pode ser criada manualmente ou será criada automaticamente no primeiro upload (se o app tiver permissão).

**Para criar manualmente:**
1. Acesse https://www.dropbox.com
2. Crie a pasta desejada (ex: "CEIE_Votacao_Backups")
3. Anote o caminho completo (ex: `/CEIE_Votacao_Backups`)

**Nota:** Se você habilitou todas as permissões no Passo 2, a pasta será criada automaticamente.

### Passo 5: Configurar no secrets.toml

Adicione a configuração no arquivo `.streamlit/secrets.toml`:

```toml
[DROPBOX]
ACCESS_TOKEN = "seu_token_aqui"
FOLDER = "/CEIE Votacao Backups"  # Pasta onde o backup será salvo (opcional)
```

**Configurações:**
- `ACCESS_TOKEN`: Token gerado no passo anterior (obrigatório)
- `FOLDER`: Caminho da pasta no Dropbox onde o arquivo será salvo (opcional)
  - Padrão: `/CEIE Votacao Backups` se não especificado
  - Deve começar com `/` (ex: `/Minha Pasta/Backups`)
  - **A pasta deve existir no Dropbox** ou o app precisa ter permissão para criar pastas

**Importante:** 
- O token é sensível - não compartilhe publicamente
- Se perder o token, gere um novo na página do app

### Passo 6: Testar

Execute a aplicação e verifique se o backup automático está funcionando.

## Estratégia de Upload

- **Upload imediato**: Quando admin fecha/abre votação ou inicia nova votação
- **Upload periódico**: A cada 15 minutos durante votação ativa (se houver votos novos)
- **Restauração**: Na inicialização, se banco local estiver vazio

## Localização do Arquivo no Dropbox

O arquivo será salvo na pasta configurada (padrão: `/CEIE Votacao Backups/votos_ceie.db`).

**Exemplos de configuração:**
- Pasta padrão: `/CEIE Votacao Backups/votos_ceie.db`
- Pasta customizada: Se configurar `FOLDER = "/Meus Backups"`, será salvo em `/Meus Backups/votos_ceie.db`
- Pasta aninhada: `FOLDER = "/Projetos/CEIE/Backups"` → `/Projetos/CEIE/Backups/votos_ceie.db`

**Nota:** Se você habilitou todas as permissões (incluindo criação de pastas), a pasta será criada automaticamente. Caso contrário, crie a pasta manualmente no Dropbox antes de usar.

Para verificar:
1. Acesse https://www.dropbox.com
2. Navegue até a pasta configurada (ou `/CEIE Votacao Backups` se usar padrão)
3. Procure pelo arquivo `votos_ceie.db`

