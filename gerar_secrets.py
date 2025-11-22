#!/usr/bin/env python3
"""
Script auxiliar para gerar os secrets do Streamlit Cloud a partir dos CSVs.

Este script lê os arquivos CSV locais e gera o formato TOML para ser
colado nos Secrets do Streamlit Cloud.

Uso:
    python gerar_secrets.py

IMPORTANTE: Não commite este script com dados reais em produção!
"""

import pandas as pd
from pathlib import Path

def ler_csv_como_string(caminho):
    """Lê um arquivo CSV e retorna como string."""
    if not Path(caminho).exists():
        print(f"⚠️  Arquivo {caminho} não encontrado!")
        return None
    
    with open(caminho, 'r', encoding='utf-8') as f:
        return f.read()

def main():
    print("=" * 60)
    print("Gerador de Secrets para Streamlit Cloud")
    print("=" * 60)
    print()
    
    # Lê os CSVs
    eleitores_csv = ler_csv_como_string('eleitores.csv')
    candidatos_csv = ler_csv_como_string('candidatos.csv')
    
    # Lê secrets.toml para pegar outras configurações
    secrets_config = {}
    if Path('.streamlit/secrets.toml').exists():
        import tomllib
        with open('.streamlit/secrets.toml', 'rb') as f:
            secrets_config = tomllib.load(f)
    
    print("📋 Cole o seguinte conteúdo nos Secrets do Streamlit Cloud:")
    print()
    print("-" * 60)
    print()
    
    # Gera o formato TOML para secrets
    print("# Configurações de Admin")
    print(f"EMAIL_ADMIN = \"{secrets_config.get('EMAIL_ADMIN', 'admin')}\"")
    print(f"PASSWORD_ADMIN = \"{secrets_config.get('PASSWORD_ADMIN', 'admin123')}\"")
    print(f"MAX_SELECTIONS = {secrets_config.get('MAX_SELECTIONS', 3)}")
    print()
    
    if eleitores_csv:
        print("# CSV de Eleitores")
        print("ELEITORES_CSV = \"\"\"")
        print(eleitores_csv.rstrip())
        print("\"\"\"")
        print()
    
    if candidatos_csv:
        print("# CSV de Candidatos")
        print("CANDIDATOS_CSV = \"\"\"")
        print(candidatos_csv.rstrip())
        print("\"\"\"")
        print()
    
    print("-" * 60)
    print()
    print("✅ Copie o conteúdo acima e cole em:")
    print("   Streamlit Cloud → Seu App → Settings → Secrets")
    print()
    print("⚠️  IMPORTANTE: Não compartilhe esses secrets publicamente!")

if __name__ == "__main__":
    try:
        main()
    except ImportError:
        print("⚠️  Para Python < 3.11, instale tomli: pip install tomli")
        print("   Ou edite manualmente o arquivo .streamlit/secrets.toml")
