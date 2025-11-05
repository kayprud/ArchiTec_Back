from flask import Flask, request, jsonify, send_file, render_template, send_from_directory
from flask_cors import CORS
from zai import ZhipuAiClient
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
import io
import os
import json
import re
from datetime import datetime
import uuid

# --- CONFIGURAÇÃO ---
app = Flask(__name__)
CORS(app)
EXCEL_FILE = r'C:\Users\a2016825\ML\Archi\back\orcamento.xlsx'
GLM_API_KEY = "8bcf0c8788844f5083a78b457316f74e.RLXYMfd70rneG1Vq"

# Inicializar cliente Zhipu AI
try:
    client = ZhipuAiClient(api_key=GLM_API_KEY)
    print(" Cliente Zhipu AI inicializado com sucesso!")
except Exception as e:
    print(f" Erro ao inicializar cliente Zhipu AI: {e}")
    client = None

# --- CONSTANTES ---
COLUNAS_ESPERADAS = {
    'descricao': ['descrição', 'descricao', 'produto', 'item', 'nome', 'description', 'product'],
    'dimensao': ['dimensão', 'dimensao', 'tamanho', 'medida', 'size', 'dimension'],
    'valor': ['valor final', 'valor', 'preço', 'preco', 'custo', 'price', 'cost']
}

# Estados da conversa
ESTADOS = {
    'INICIO': 'INICIO',
    'MULTIPLAS_OPCOES': 'MULTIPLAS_OPCOES',
    'PRODUTO_SELECIONADO': 'PRODUTO_SELECIONADO',
    'DIMENSAO_SOLICITADA': 'DIMENSAO_SOLICITADA',
    'ORCAMENTO_FINALIZADO': 'ORCAMENTO_FINALIZADO'
}

# --- CLASSES PARA MELHOR ORGANIZAÇÃO ---
class Produto:
    def __init__(self, descricao, dimensao=None, valor=None):
        self.descricao = descricao
        self.dimensao = dimensao
        self.valor = valor
    
    def to_dict(self):
        return {
            'descricao': self.descricao,
            'dimensao': self.dimensao,
            'valor': self.valor
        }
    
    def formatar_valor(self):
        if isinstance(self.valor, (int, float)):
            return f"R$ {self.valor:.2f}"
        return f"R$ {self.valor}" if self.valor else "Valor não informado"

class Conversa:
    def __init__(self):
        self.estado = ESTADOS['INICIO']
        self.produtos_encontrados = []  # Lista de produtos encontrados na busca
        self.produto_selecionado = None  # Produto escolhido pelo usuário
        self.quantidade = 1  # Quantidade desejada
        self.dimensao_selecionada = None
    
    def reiniciar(self):
        self.estado = ESTADOS['INICIO']
        self.produtos_encontrados = []
        self.produto_selecionado = None
        self.quantidade = 1
        self.dimensao_selecionada = None

# Armazenamento de conversas
conversas = {}

# --- FUNÇÕES AUXILIARES ---
def carregar_excel():
    """Carrega os dados do arquivo Excel"""
    try:
        if not os.path.exists(EXCEL_FILE):
            print(f" Arquivo {EXCEL_FILE} não encontrado!")
            return pd.DataFrame()
        
        if EXCEL_FILE.endswith('.xlsx'):
            df = pd.read_excel(EXCEL_FILE, engine='openpyxl')
        elif EXCEL_FILE.endswith('.xls'):
            df = pd.read_excel(EXCEL_FILE, engine='xlrd')
        elif EXCEL_FILE.endswith('.csv'):
            df = pd.read_csv(EXCEL_FILE, encoding='utf-8', delimiter=';')
        else:
            print(f" Formato não suportado: {EXCEL_FILE}")
            return pd.DataFrame()
        
        print(f" Excel carregado: {len(df)} registros")
        return df
        
    except Exception as e:
        print(f" Erro ao carregar Excel: {e}")
        return pd.DataFrame()

def identificar_colunas(df):
    """Identifica as colunas importantes no DF"""
    colunas_identificadas = {}
    
    for tipo, possiveis_nomes in COLUNAS_ESPERADAS.items():
        for col in df.columns:
            col_lower = str(col).lower()
            for nome in possiveis_nomes:
                if nome in col_lower:
                    colunas_identificadas[tipo] = col
                    print(f"🎯 Coluna de {tipo} encontrada: '{col}'")
                    break
            if tipo in colunas_identificadas:
                break
    
    for tipo in ['descricao', 'valor']:
        if tipo not in colunas_identificadas:
            print(f" Coluna de {tipo} não encontrada. Colunas disponíveis: {list(df.columns)}")
    
    return colunas_identificadas

def buscar_produtos_por_nome(nome_produto):
    """Busca produtos pelo nome no Excel com busca mais flexível"""
    try:
        df = carregar_excel()
        if df.empty:
            return []
        
        colunas = identificar_colunas(df)
        if 'descricao' not in colunas:
            return []
        
        print(f" Buscando: '{nome_produto}'")
        
        resultados = []
        termos_busca = [t for t in nome_produto.lower().split() if len(t) > 2]
        
        for idx, produto in df.iterrows():
            descricao_completa = str(produto[colunas['descricao']]).lower()
            
            # Verificar se todos os termos estão na descrição
            if all(termo in descricao_completa for termo in termos_busca):
                resultados.append(Produto(
                    descricao=produto[colunas['descricao']],
                    dimensao=produto.get(colunas.get('dimensao', ''), None),
                    valor=produto.get(colunas['valor'], None)
                ))
        
        # tenta busca parcial
        if not resultados and len(termos_busca) > 1:
            for termo in termos_busca:
                mask_parcial = df[colunas['descricao']].astype(str).str.lower().str.contains(termo, na=False)
                if mask_parcial.any():
                    for idx, produto in df[mask_parcial].iterrows():
                        if not any(p.descricao == produto[colunas['descricao']] for p in resultados):
                            resultados.append(Produto(
                                descricao=produto[colunas['descricao']],
                                dimensao=produto.get(colunas.get('dimensao', ''), None),
                                valor=produto.get(colunas['valor'], None)
                            ))
        
        print(f" {len(resultados)} produto(s) encontrado(s)")
        return resultados
        
    except Exception as e:
        print(f" Erro ao buscar produto: {e}")
        return []

def analisar_falha_busca(termo_busca):
    """Analisa por que a busca falhou e sugere alternativas"""
    try:
        df = carregar_excel()
        if df.empty:
            return "Arquivo de produtos não encontrado"
        
        colunas = identificar_colunas(df)
        if 'descricao' not in colunas:
            return "Coluna de descrição não identificada"
        
        produtos = df[colunas['descricao']].dropna().astype(str).tolist()
        
        # Buscar produtos que contenham partes do termo
        termos = termo_busca.lower().split()
        sugestoes = []
        
        for produto in produtos:
            produto_lower = produto.lower()
            for termo in termos:
                if termo in produto_lower and len(termo) > 2:
                    sugestoes.append(produto)
                    break
        
        if sugestoes:
            return f"Produtos similares encontrados: {', '.join(sugestoes[:5])}"
        else:
            # Buscar por palavras individuais
            palavras_chave = []
            for termo in termos:
                if len(termo) > 2:
                    for produto in produtos:
                        if termo in produto.lower():
                            palavras_chave.append(termo)
                            break
            
            if palavras_chave:
                return f"Tente pesquisar por: {' ou '.join(palavras_chave[:3])}"
            else:
                return "Nenhum produto similar encontrado. Verifique a ortografia."
    
    except Exception as e:
        return f"Erro na análise: {e}"
    
def extrair_produtos_manualmente(mensagem):
    """Extração manual de múltiplos produtos como fallback"""
    produtos_extraidos = []
    
    print(f" Iniciando extração manual de: '{mensagem}'")
    
    # Divide a mensagem em partes usando múltiplos separadores
    separadores = [
        r',\s*',  # Vírgula seguida de espaços
        r'\s+e\s+',  # " e " entre palavras
        r'\s+e mais\s+',
        r'\s+também\s+',
        r'\s+além de\s+',
        r'\s+e\s+',  # Segundo "e" para garantir
    ]
    
    partes = [mensagem]
    
    for sep in separadores:
        novas_partes = []
        for parte in partes:
            dividido = re.split(sep, parte, flags=re.IGNORECASE)
            novas_partes.extend(dividido)
        partes = [p.strip() for p in novas_partes if p.strip()]
    
    print(f" Partes detectadas: {partes}")
    
    # Padrões para identificar produtos e quantidades
    padroes_produto = [
        # Padrão: quantidade + produto
        r'^(\d+)\s+(.+)$',
        # Padrão: produto + quantidade
        r'^(.+?)\s+(\d+)$',
        # Padrão: "quero/preciso" + quantidade + produto
        r'^(?:quero|preciso|gostaria|precisaria)\s+(\d+)\s+(.+)$',
        # Padrão: "quero/preciso" + produto + quantidade
        r'^(?:quero|preciso|gostaria|precisaria)\s+(.+?)\s+(\d+)$',
    ]
    
    for parte in partes:
        print(f" Analisando parte: '{parte}'")
        
        produto_encontrado = None
        quantidade_encontrada = 1
        
        # Tenta cada padrão
        for padrao in padroes_produto:
            match = re.match(padrao, parte.strip(), re.IGNORECASE)
            if match:
                grupos = match.groups()
                
                if len(grupos) == 2:
                    # Determina qual grupo é quantidade e qual é produto
                    if grupos[0].isdigit():
                        quantidade_encontrada = int(grupos[0])
                        produto_encontrado = grupos[1].strip()
                    else:
                        produto_encontrado = grupos[0].strip()
                        quantidade_encontrada = int(grupos[1])
                    
                    print(f" Padrão encontrado: '{produto_encontrado}' - Qtd: {quantidade_encontrada}")
                    break
        
        # Se não encontrou padrão, assume que é o produto sem quantidade
        if not produto_encontrado:
            produto_encontrado = parte.strip()
            quantidade_encontrada = 1
            print(f" Sem padrão, assumindo: '{produto_encontrado}' - Qtd: {quantidade_encontrada}")
        
        # Limpa o nome do produto
        if produto_encontrado:
            # Remove palavras desnecessárias
            produto_limpo = re.sub(
                r'\b(quero|preciso|gostaria|precisaria|de|das|dos|unidades|pcs|peças|itens|unidade|pc|peça|item)\b',
                '',
                produto_encontrado,
                flags=re.IGNORECASE
            ).strip()
            
            # Remove números no início ou fim
            produto_limpo = re.sub(r'^\d+\s+|\s+\d+$', '', produto_limpo).strip()
            
            if produto_limpo:
                print(f" Buscando produto: '{produto_limpo}'")
                
                # Busca o produto no Excel
                produtos_encontrados = buscar_produtos_por_nome(produto_limpo)
                
                if produtos_encontrados:
                    produto = produtos_encontrados[0]  # Pega o primeiro encontrado
                    
                    # Verifica se já não foi adicionado
                    ja_existe = False
                    for p in produtos_extraidos:
                        if p['name'].lower() == produto.descricao.lower():
                            # Atualiza quantidade se já existe
                            p['quantity'] += quantidade_encontrada
                            ja_existe = True
                            print(f" Produto atualizado: {produto.descricao} - Nova Qtd: {p['quantity']}")
                            break
                    
                    if not ja_existe:
                        produtos_extraidos.append({
                            'name': produto.descricao,
                            'quantity': quantidade_encontrada,
                            'price': float(produto.valor) if produto.valor else 0,
                            'dimensions': produto.dimensao
                        })
                        print(f" Produto adicionado: {produto.descricao} - Qtd: {quantidade_encontrada}")
                else:
                    print(f" Produto não encontrado: '{produto_limpo}'")
    
    print(f" Total de produtos extraídos: {len(produtos_extraidos)}")
    return produtos_extraidos

def extrair_produtos_da_mensagem(mensagem):
    """Usa GLM para extrair múltiplos produtos e quantidades de uma mensagem"""
    if not client:
        # Fallback sem GLM - extração manual
        print(" GLM não disponível, usando extração manual")
        return extrair_produtos_manualmente(mensagem)
    
    try:
        df = carregar_excel()
        if df.empty:
            print(" Excel vazio, usando extração manual")
            return extrair_produtos_manualmente(mensagem)
        
        colunas = identificar_colunas(df)
        if 'descricao' not in colunas:
            print(" Coluna descrição não encontrada, usando extração manual")
            return extrair_produtos_manualmente(mensagem)
        
        produtos = df[colunas['descricao']].dropna().astype(str).tolist()
        
        # Prompt melhorado para múltiplos produtos
        prompt_sistema = f"""Você é um especialista em extrair informações de orçamentos. Analise a mensagem e extraia TODOS os produtos mencionados.

PRODUTOS DISPONÍVEIS:
{chr(10).join([f"- {produto}" for produto in produtos[:30]])}

INSTRUÇÕES IMPORTANTES:
- Extraia TODOS os produtos da mensagem
- Cada produto deve ter nome e quantidade
- Use números por extenso: cinco=5, dez=10, três=3
- Se não mencionar quantidade, use 1
- Retorne APENAS JSON válido

FORMATO OBRIGATÓRIO:
{{
  "products": [
    {{"name": "nome_exato_produto1", "quantity": numero}},
    {{"name": "nome_exato_produto2", "quantity": numero}}
  ]
}}

EXEMPLOS:
Mensagem: "5 hafele gt2, 10 divisores von ort e preciso de 3 corrediças"
Resposta: {{"products": [{{"name": "hafele gt2", "quantity": 5}}, {{"name": "divisores von ort", "quantity": 10}}, {{"name": "corrediças", "quantity": 3}}]}}

Mensagem: "{mensagem}"
Resposta:"""
        
        response = client.chat.completions.create(
            model="glm-4",
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": mensagem}
            ],
            max_tokens=400,
            temperature=0.1
        )

        resposta_texto = response.choices[0].message.content.strip()
        print(f" Resposta GLM (múltiplos produtos): {resposta_texto}")
        
        try:
            json_match = re.search(r'\{.*\}', resposta_texto, re.DOTALL)
            if json_match:
                resultado = json.loads(json_match.group())
                if 'products' in resultado and resultado['products']:
                    produtos_extraidos = []
                    for item in resultado['products']:
                        # Buscar cada produto no Excel
                        produtos_encontrados = buscar_produtos_por_nome(item['name'])
                        if produtos_encontrados:
                            produto = produtos_encontrados[0]
                            produtos_extraidos.append({
                                'name': produto.descricao,
                                'quantity': max(1, int(item.get('quantity', 1))),
                                'price': float(produto.valor) if produto.valor else 0,
                                'dimensions': produto.dimensao
                            })
                            print(f" Produto GLM: {produto.descricao} - Qtd: {item.get('quantity', 1)}")
                        else:
                            print(f" Produto não encontrado: {item['name']}")
                    
                    if produtos_extraidos:
                        return produtos_extraidos
        except json.JSONDecodeError as e:
            print(f" Erro JSON GLM: {e}")
        
        # Fallback para extração manual
        print(" Usando fallback manual para múltiplos produtos")
        return extrair_produtos_manualmente(mensagem)
        
    except Exception as e:
        print(f" Erro ao extrair múltiplos produtos: {e}")
        return extrair_produtos_manualmente(mensagem)

def processar_intencao_com_glm(mensagem, session_id=None):
    """Usa a API GLM para identificar a intenção, produto e quantidade"""
    if not client:
        # Fallback sem GLM
        quantidade = extrair_quantidade_da_mensagem(mensagem)
        return {"intent": "fazer_orcamento", "produto": mensagem, "quantidade": quantidade}
    
    try:
        df = carregar_excel()
        if df.empty:
            quantidade = extrair_quantidade_da_mensagem(mensagem)
            return {"intent": "fazer_orcamento", "produto": mensagem, "quantidade": quantidade}
        
        colunas = identificar_colunas(df)
        if 'descricao' not in colunas:
            quantidade = extrair_quantidade_da_mensagem(mensagem)
            return {"intent": "fazer_orcamento", "produto": mensagem, "quantidade": quantidade}
        
        produtos = df[colunas['descricao']].dropna().astype(str).tolist()
        
        if session_id and session_id in conversas:
            conversa = conversas[session_id]
            if conversa.estado == ESTADOS['DIMENSAO_SOLICITADA']:
                return {"intent": "fornecer_dimensao", "dimensao": mensagem}
        
        # Prompt simplificado mas mais eficaz
        prompt_sistema = f"""Extraia o produto e a quantidade da mensagem.

PRODUTOS DISPONÍVEIS:
{chr(10).join([f"- {produto}" for produto in produtos[:20]])}

RETORNE APENAS JSON:
{{
  "intent": "fazer_orcamento",
  "produto": "nome_produto",
  "quantidade": numero
}}

Mensagem: "{mensagem}"
JSON:"""
        
        response = client.chat.completions.create(
            model="glm-4",
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": mensagem}
            ],
            max_tokens=100,
            temperature=0.1
        )

        resposta_texto = response.choices[0].message.content.strip()
        print(f" Resposta GLM bruta: {resposta_texto}")
        
        # Tentativa 1: JSON completo
        try:
            json_match = re.search(r'\{.*\}', resposta_texto, re.DOTALL)
            if json_match:
                resultado = json.loads(json_match.group())
                
                # Processa quantidade
                if 'quantidade' in resultado:
                    quantidade = resultado['quantidade']
                    if isinstance(quantidade, str):
                        # Extrai números da string
                        nums = re.findall(r'\d+', quantidade)
                        quantidade = int(nums[0]) if nums else 1
                    else:
                        quantidade = int(quantidade)
                    
                    quantidade = max(1, quantidade)  # Garante mínimo 1
                    resultado['quantidade'] = quantidade
                    
                    print(f" GLM funcionou - Produto: {resultado.get('produto')}, Qtd: {quantidade}")
                    return resultado
        except Exception as e:
            print(f" Erro no JSON do GLM: {e}")
        
        # Fallback: extração manual
        print(" Usando fallback de extração manual")
        quantidade_fallback = extrair_quantidade_da_mensagem(mensagem)
        print(f" Quantidade extraída manualmente: {quantidade_fallback}")
        
        return {
            "intent": "fazer_orcamento", 
            "produto": mensagem, 
            "quantidade": quantidade_fallback
        }
        
    except Exception as e:
        print(f" Erro completo no GLM: {e}")
        quantidade = extrair_quantidade_da_mensagem(mensagem)
        return {"intent": "fazer_orcamento", "produto": mensagem, "quantidade": quantidade}



def gerar_tabela_resumo(conversa):
    """Gera uma tabela formatada com o resumo do orçamento"""
    if not conversa.produto_selecionado:
        return ""
    
    produto = conversa.produto_selecionado
    quantidade = conversa.quantidade
    
    # Debug forçado
    print(f" DEBUG - gerar_tabela_resumo:")
    print(f"   Produto: {produto.descricao}")
    print(f"   Quantidade (conversa): {quantidade} (tipo: {type(quantidade)})")
    print(f"   Valor (produto): {produto.valor} (tipo: {type(produto.valor)})")
    
    # Garante que quantidade seja inteiro
    try:
        quantidade = int(quantidade)
    except (ValueError, TypeError):
        quantidade = 1
        print(f" Quantidade inválida, usando 1")
    
    # Garante que valor seja float
    try:
        valor_unitario = float(produto.valor) if produto.valor else 0
    except (ValueError, TypeError):
        valor_unitario = 0
        print(f" Valor inválido, usando 0")
    
    # Cálculo do valor total
    valor_total = valor_unitario * quantidade
    
    print(f"   Valor unitário (convertido): {valor_unitario}")
    print(f"   Quantidade (convertida): {quantidade}")
    print(f"   Valor total calculado: {valor_total}")
    
    # Formatação
    valor_unitario_str = f"R$ {valor_unitario:.2f}"
    valor_total_str = f"R$ {valor_total:.2f}"
    
    # Tabela detalhada
    tabela = f""" *Resumo do Orçamento:*

| Qtd | Produto | Vl. Unitário | Vl. Total |
|-----|---------|--------------|-----------|
| {quantidade} | {produto.descricao[:40] + '...' if len(produto.descricao) > 40 else produto.descricao} | {valor_unitario_str} | {valor_total_str} |

💰 *Valor Total: {valor_total_str}*
🧮 *Cálculo: {quantidade} × {valor_unitario_str} = {valor_total_str}*

📄 PDF disponível para download abaixo"""
    
    return tabela


def gerar_tabela_multiplos_produtos(produtos_quantidades):
    """Gera tabela formatada para múltiplos produtos"""
    tabela = " *Resumo do Orçamento:*\n\n"
    tabela += "| Qtd | Produto | Dimensões | Vl. Unitário | Vl. Total |\n"
    tabela += "|-----|---------|-----------|--------------|-----------|\n"
    
    valor_total_geral = 0
    
    for produto, quantidade in produtos_quantidades:
        valor_unitario = float(produto.valor) if produto.valor else 0
        valor_total = valor_unitario * quantidade
        valor_total_geral += valor_total
        
        nome = produto.descricao[:30] + "..." if len(produto.descricao) > 30 else produto.descricao
        dimensoes = produto.dimensao if produto.dimensao else "N/A"
        
        tabela += f"| {quantidade} | {nome} | {dimensoes} | R$ {valor_unitario:.2f} | R$ {valor_total:.2f} |\n"
    
    tabela += f"\n💰 *Valor Total do Orçamento: R$ {valor_total_geral:.2f}*\n\n"
    tabela += "📄 PDF disponível para download abaixo"
    
    return tabela

def gerar_resposta_multiplas_opcoes(produtos):
    """Gera resposta para quando múltiplos produtos são encontrados"""
    resposta = "🔍 *Encontrei múltiplos produtos correspondentes. Por favor, escolha uma opção:*\n\n"
    
    for i, produto in enumerate(produtos, 1):
        resposta += f"*{i}.* {produto.descricao}\n"
        if produto.dimensao:
            resposta += f"   📏 Dimensão: {produto.dimensao}\n"
        if produto.valor:
            resposta += f"   💰 Valor: {produto.formatar_valor()}\n"
        resposta += "\n"
    
    resposta += " *Digite o número da opção desejada para continuar.*"
    return resposta

def gerar_pdf(produtos, nome_cliente="Orçamento", quantidade=1):
    """Gera um PDF profissional com os produtos e quantidade"""
    try:
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter

        # Cores
        cor_primaria = HexColor('#2E86AB')
        cor_secundaria = HexColor('#A23B72')
        cor_texto = HexColor('#333333')

        # Cabeçalho
        p.setFillColor(cor_primaria)
        p.rect(0, height - 100, width, 100, fill=True, stroke=False)
        
        p.setFillColorRGB(1, 1, 1)
        p.setFont("Helvetica-Bold", 20)
        p.drawString(inch, height - 1.5 * inch, "ORÇAMENTO")
        
        p.setFont("Helvetica", 12)
        p.drawString(inch, height - 1.8 * inch, f"Data: {datetime.now().strftime('%d/%m/%Y')}")
        p.drawString(inch, height - 2 * inch, f"Cliente: {nome_cliente}")

        # Título da tabela
        p.setFillColor(cor_secundaria)
        p.rect(0, height - 250, width, 40, fill=True, stroke=False)
        
        p.setFillColorRGB(1, 1, 1)
        p.setFont("Helvetica-Bold", 12)
        p.drawString(inch, height - 2.7 * inch, "Qtd")
        p.drawString(1.5 * inch, height - 2.7 * inch, "Produto")
        p.drawString(4 * inch, height - 2.7 * inch, "Dimensões")
        p.drawString(5.5 * inch, height - 2.7 * inch, "Vl. Unit.")
        p.drawString(6.5 * inch, height - 2.7 * inch, "Vl. Total")

        # Itens
        p.setFillColor(cor_texto)
        p.setFont("Helvetica", 10)
        y_position = height - 3.2 * inch
        
        valor_total_geral = 0
        
        for produto in produtos:
            # Quantidade
            p.drawString(inch, y_position, str(quantidade))
            
            # Descrição do produto
            descricao = produto.descricao
            if len(descricao) > 30:
                descricao = descricao[:27] + "..."
            p.drawString(1.5 * inch, y_position, descricao)
            
            # Dimensões
            dimensao = produto.dimensao if produto.dimensao else "N/A"
            p.drawString(4 * inch, y_position, dimensao)
            
            # Valor unitário
            valor_unitario = float(produto.valor) if produto.valor else 0
            valor_unitario_str = f"R$ {valor_unitario:.2f}"
            p.drawString(5.5 * inch, y_position, valor_unitario_str)
            
            # Valor total
            valor_total = valor_unitario * quantidade
            valor_total_str = f"R$ {valor_total:.2f}"
            p.drawString(6.5 * inch, y_position, valor_total_str)
            
            valor_total_geral += valor_total
            y_position -= 0.4 * inch

        # Total geral
        p.setFillColor(cor_secundaria)
        p.rect(0, y_position - 20, width, 30, fill=True, stroke=False)
        p.setFillColorRGB(1, 1, 1)
        p.setFont("Helvetica-Bold", 12)
        p.drawString(5.5 * inch, y_position - 10, "TOTAL:")
        p.drawString(6.5 * inch, y_position - 10, f"R$ {valor_total_geral:.2f}")

        # Rodapé
        p.setFillColor(cor_primaria)
        p.rect(0, 50, width, 50, fill=True, stroke=False)
        
        p.setFillColorRGB(1, 1, 1)
        p.setFont("Helvetica", 10)
        p.drawString(inch, 70, "Este orçamento é válido por 30 dias.")
        p.drawString(inch, 55, "Para dúvidas, entre em contato: orcamento@empresa.com")

        p.save()
        buffer.seek(0)
        return buffer
    except Exception as e:
        print(f" Erro ao gerar PDF: {e}")
        return None

def gerar_pdf_multiplos(produtos_quantidades, nome_cliente="Orçamento"):
    """Gera PDF para múltiplos produtos"""
    try:
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter

        # Cores
        cor_primaria = HexColor('#2E86AB')
        cor_secundaria = HexColor('#A23B72')
        cor_texto = HexColor('#333333')

        # Cabeçalho
        p.setFillColor(cor_primaria)
        p.rect(0, height - 100, width, 100, fill=True, stroke=False)
        
        p.setFillColorRGB(1, 1, 1)
        p.setFont("Helvetica-Bold", 20)
        p.drawString(inch, height - 1.5 * inch, "ORÇAMENTO MÚLTIPLO")
        
        p.setFont("Helvetica", 12)
        p.drawString(inch, height - 1.8 * inch, f"Data: {datetime.now().strftime('%d/%m/%Y')}")
        p.drawString(inch, height - 2 * inch, f"Cliente: {nome_cliente}")

        # Título da tabela
        p.setFillColor(cor_secundaria)
        p.rect(0, height - 250, width, 40, fill=True, stroke=False)
        
        p.setFillColorRGB(1, 1, 1)
        p.setFont("Helvetica-Bold", 12)
        p.drawString(inch, height - 2.7 * inch, "Qtd")
        p.drawString(1.5 * inch, height - 2.7 * inch, "Produto")
        p.drawString(4 * inch, height - 2.7 * inch, "Dimensões")
        p.drawString(5.5 * inch, height - 2.7 * inch, "Vl. Unit.")
        p.drawString(6.5 * inch, height - 2.7 * inch, "Vl. Total")

        # Itens
        p.setFillColor(cor_texto)
        p.setFont("Helvetica", 10)
        y_position = height - 3.2 * inch
        
        valor_total_geral = 0
        
        for produto, quantidade in produtos_quantidades:
            # Quantidade
            p.drawString(inch, y_position, str(quantidade))
            
            # Descrição do produto
            descricao = produto.descricao
            if len(descricao) > 30:
                descricao = descricao[:27] + "..."
            p.drawString(1.5 * inch, y_position, descricao)
            
            # Dimensões
            dimensao = produto.dimensao if produto.dimensao else "N/A"
            p.drawString(4 * inch, y_position, dimensao)
            
            # Valor unitário
            valor_unitario = float(produto.valor) if produto.valor else 0
            valor_unitario_str = f"R$ {valor_unitario:.2f}"
            p.drawString(5.5 * inch, y_position, valor_unitario_str)
            
            # Valor total
            valor_total = valor_unitario * quantidade
            valor_total_str = f"R$ {valor_total:.2f}"
            p.drawString(6.5 * inch, y_position, valor_total_str)
            
            valor_total_geral += valor_total
            y_position -= 0.4 * inch

        # Total geral
        p.setFillColor(cor_secundaria)
        p.rect(0, y_position - 20, width, 30, fill=True, stroke=False)
        p.setFillColorRGB(1, 1, 1)
        p.setFont("Helvetica-Bold", 12)
        p.drawString(5.5 * inch, y_position - 10, "TOTAL:")
        p.drawString(6.5 * inch, y_position - 10, f"R$ {valor_total_geral:.2f}")

        # Rodapé
        p.setFillColor(cor_primaria)
        p.rect(0, 50, width, 50, fill=True, stroke=False)
        
        p.setFillColorRGB(1, 1, 1)
        p.setFont("Helvetica", 10)
        p.drawString(inch, 70, "Este orçamento é válido por 30 dias.")
        p.drawString(inch, 55, "Para dúvidas, entre em contato: orcamento@empresa.com")

        p.save()
        buffer.seek(0)
        return buffer
    except Exception as e:
        print(f" Erro ao gerar PDF: {e}")
        return None
def extrair_quantidade_da_mensagem(mensagem):
    """Extrai quantidade da mensagem usando múltiplos métodos"""
    
    # Método 1: Números explícitos
    numeros = re.findall(r'\b(\d+)\b', mensagem)
    if numeros:
        try:
            return int(numeros[0])
        except ValueError:
            pass
    
    # Método 2: Números por extenso
    numeros_por_extenso = {
        'zero': 0, 'um': 1, 'uma': 1, 'dois': 2, 'duas': 2, 'três': 3, 'tres': 3,
        'quatro': 4, 'cinco': 5, 'seis': 6, 'sete': 7, 'oito': 8, 'nove': 9, 'dez': 10,
        'onze': 11, 'doze': 12, 'treze': 13, 'quatorze': 14, 'catorze': 14, 'quinze': 15,
        'dezesseis': 16, 'dezessete': 17, 'dezoito': 18, 'dezenove': 19, 'vinte': 20
    }
    
    mensagem_lower = mensagem.lower()
    for palavra, numero in numeros_por_extenso.items():
        if f' {palavra} ' in f' {mensagem_lower} ' or mensagem_lower.startswith(palavra + ' ') or mensagem_lower.endswith(' ' + palavra):
            return numero
    
    # Método 3:
    padroes = [
        r'(\d+)\s+(?:unidades?|pcs?|peças?|itens?)',
        r'(?:quero|preciso|gostaria|precisaria)\s+(\d+)',
        r'(\d+)\s+(?:hafele|divisor|corrediça|dobradiça)',
    ]
    
    for padrao in padroes:
        match = re.search(padrao, mensagem_lower)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                pass
    
    return 1  


# --- ENDPOINTS DA API ---
@app.route('/')
def index():
    """Serve the main chat interface"""
    return render_template('index.html')

@app.route('/static/<path:filename>')
def static_files(filename):
    """Serve static files"""
    return send_from_directory('static', filename)

@app.route('/extract-products', methods=['POST'])
def extract_products():
    """Endpoint para extrair múltiplos produtos de uma mensagem"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Dados JSON inválidos"}), 400
    
    message = data.get('message', '')
    session_id = data.get('session_id', 'default')
    
    if not message:
        return jsonify({"error": "Mensagem não pode ser vazia"}), 400
    
    try:
        produtos = extrair_produtos_da_mensagem(message)
        return jsonify({"products": produtos})
    except Exception as e:
        print(f" Erro no endpoint /extract-products: {e}")
        return jsonify({"error": "Ocorreu um erro interno"}), 500

@app.route('/chat', methods=['POST', 'OPTIONS'])
def chat():
    if request.method == 'OPTIONS':
        return '', 200
        
    data = request.get_json()
    if not data:
        return jsonify({"error": "Dados JSON inválidos"}), 400
        
    user_message = data.get('message', '')
    session_id = data.get('session_id', 'default')
    mode = data.get('mode', 'single')
    products_data = data.get('products', [])

    if not user_message and not products_data:
        return jsonify({"error": "Mensagem não pode ser vazia."}), 400

    try:
        print(f" Mensagem recebida: {user_message} (Sessão: {session_id}, Modo: {mode})")
        
        if session_id not in conversas:
            conversas[session_id] = Conversa()
        
        conversa = conversas[session_id]
        
        
        if mode == 'multiple' and user_message == 'generate_multiple_quote' and products_data:
            conversa.reiniciar()
            
            
            produtos_orcamento = []
            for item in products_data:
                produto = Produto(
                    descricao=item['name'],
                    dimensao=item.get('dimensions'),
                    valor=item['price']
                )
                produtos_orcamento.append((produto, item['quantity']))
            
            
            response_text = gerar_tabela_multiplos_produtos(produtos_orcamento)
            
            # PDF
            pdf_buffer = gerar_pdf_multiplos(produtos_orcamento, nome_cliente=f"Cliente {session_id}")
            if pdf_buffer:
                pdf_path = f"orcamento_temp_{session_id}.pdf"
                with open(pdf_path, "wb") as f:
                    f.write(pdf_buffer.getvalue())
                
                return jsonify({
                    "response": response_text, 
                    "pdf_url": f"/download/pdf/{session_id}",
                    "session_id": session_id
                })
            else:
                return jsonify({
                    "response": response_text,
                    "pdf_url": None,
                    "session_id": session_id
                })
        
        # Verificar se está esperando escolha de produto
        if conversa.estado == ESTADOS['MULTIPLAS_OPCOES']:
            if user_message.isdigit():
                opcao = int(user_message)
                if 1 <= opcao <= len(conversa.produtos_encontrados):
                    conversa.produto_selecionado = conversa.produtos_encontrados[opcao - 1]
                    conversa.estado = ESTADOS['PRODUTO_SELECIONADO']
                    
                    # Verificar se precisa de dimensões
                    if not conversa.produto_selecionado.dimensao:
                        conversa.estado = ESTADOS['DIMENSAO_SOLICITADA']
                        response_text = f" *Produto selecionado:* {conversa.produto_selecionado.descricao}\n\n🔍 *Por favor, informe as dimensões desejadas:*"
                        return jsonify({"response": response_text, "pdf_url": None, "session_id": session_id})
                    else:
                        # Tem dimensão, pode finalizar
                        conversa.estado = ESTADOS['ORCAMENTO_FINALIZADO']
                        tabela_resumo = gerar_tabela_resumo(conversa)
                        response_text = f"{tabela_resumo}\n\n PDF disponível para download abaixo"
                        
                        pdf_buffer = gerar_pdf([conversa.produto_selecionado], nome_cliente=f"Cliente {session_id}", quantidade=conversa.quantidade)
                        if pdf_buffer:
                            pdf_path = f"orcamento_temp_{session_id}.pdf"
                            with open(pdf_path, "wb") as f:
                                f.write(pdf_buffer.getvalue())
                            return jsonify({
                                "response": response_text, 
                                "pdf_url": f"/download/pdf/{session_id}",
                                "session_id": session_id
                            })
                else:
                    response_text = " *Opção inválida.* Por favor, digite um número da lista de opções."
                    return jsonify({"response": response_text, "pdf_url": None, "session_id": session_id})
        
        # Verificar se está esperando dimensões
        if conversa.estado == ESTADOS['DIMENSAO_SOLICITADA']:
            conversa.dimensao_selecionada = user_message
            conversa.produto_selecionado.dimensao = user_message
            conversa.estado = ESTADOS['ORCAMENTO_FINALIZADO']
            
            tabela_resumo = gerar_tabela_resumo(conversa)
            response_text = f"{tabela_resumo}\n\n PDF disponível para download abaixo"
            
            pdf_buffer = gerar_pdf([conversa.produto_selecionado], nome_cliente=f"Cliente {session_id}", quantidade=conversa.quantidade)
            if pdf_buffer:
                pdf_path = f"orcamento_temp_{session_id}.pdf"
                with open(pdf_path, "wb") as f:
                    f.write(pdf_buffer.getvalue())
                return jsonify({
                    "response": response_text, 
                    "pdf_url": f"/download/pdf/{session_id}",
                    "session_id": session_id
                })
        
        # Processar nova solicitação
        intent_data = processar_intencao_com_glm(user_message, session_id)
        intent = intent_data.get("intent", "fazer_orcamento")
        
       
     

        if intent == "fazer_orcamento":
            conversa.reiniciar()
    
            produto_busca = intent_data.get("produto", user_message)
            quantidade_extraida = intent_data.get("quantidade", 1)
        
            
            print(f" PROCESSANDO ORÇAMENTO:")
            print(f"   Mensagem original: {user_message}")
            print(f"   Produto extraído: {produto_busca}")
            print(f"   Quantidade extraída: {quantidade_extraida} (tipo: {type(quantidade_extraida)})")
            print(f"   Intent data completo: {intent_data}")
            
           
            try:
                conversa.quantidade = int(quantidade_extraida)
            except (ValueError, TypeError):
                conversa.quantidade = 1
                print(f"⚠️ Erro ao converter quantidade, usando 1")
            
            print(f"   Quantidade final na conversa: {conversa.quantidade}")
            
            produtos_encontrados = buscar_produtos_por_nome(produto_busca)
            
            if not produtos_encontrados:
                response_text = f""" *Produto não encontrado*

        Não consegui encontrar "{produto_busca}" no meu arquivo de preços."""
                return jsonify({"response": response_text, "pdf_url": None, "session_id": session_id})
            
            # Encontrou apenas um produto
            conversa.produto_selecionado = produtos_encontrados[0]
            conversa.estado = ESTADOS['PRODUTO_SELECIONADO']
            
            print(f" Produto encontrado: {conversa.produto_selecionado.descricao}")
            print(f" Valor do produto: {conversa.produto_selecionado.valor}")
            
            # Verificar se precisa de dimensões
            if not conversa.produto_selecionado.dimensao:
                conversa.estado = ESTADOS['DIMENSAO_SOLICITADA']
                response_text = f" *Produto encontrado:* {conversa.produto_selecionado.descricao}\n\n🔍 *Por favor, informe as dimensões desejadas:*"
                return jsonify({"response": response_text, "pdf_url": None, "session_id": session_id})
            else:
                # Tem dimensão, pode finalizar
                conversa.estado = ESTADOS['ORCAMENTO_FINALIZADO']
                
                # Debug antes de gerar tabela
                print(f" Antes de gerar tabela:")
                print(f"   Quantidade na conversa: {conversa.quantidade}")
                print(f"   Valor no produto: {conversa.produto_selecionado.valor}")
                
                tabela_resumo = gerar_tabela_resumo(conversa)
                response_text = f"{tabela_resumo}\n\n PDF disponível para download abaixo"
        
            pdf_buffer = gerar_pdf([conversa.produto_selecionado], nome_cliente=f"Cliente {session_id}", quantidade=conversa.quantidade)
            if pdf_buffer:
                pdf_path = f"orcamento_temp_{session_id}.pdf"
                with open(pdf_path, "wb") as f:
                    f.write(pdf_buffer.getvalue())
                return jsonify({
                    "response": response_text, 
                    "pdf_url": f"/download/pdf/{session_id}",
                    "session_id": session_id
                }) 
                # Fallback
                response_text = "Desculpe, não entendi. Você pode informar o nome do produto que deseja orçar?"
                return jsonify({
                    "response": response_text,
                    "pdf_url": None,
                    "session_id": session_id
                })

    except Exception as e:
        print(f" Erro no endpoint /chat: {e}")
        return jsonify({"error": "Ocorreu um erro interno no servidor."}), 500

@app.route('/download/pdf/<session_id>')
def download_pdf(session_id):
    pdf_path = f"orcamento_temp_{session_id}.pdf"
    if os.path.exists(pdf_path):
        return send_file(pdf_path, as_attachment=True, download_name=f"orcamento_{session_id}.pdf")
    return jsonify({"error": "PDF não encontrado"}), 404

@app.route('/admin/verificar-excel', methods=['GET'])
def verificar_excel():
    """Endpoint para verificar o arquivo Excel"""
    try:
        df = carregar_excel()
        
        info = {
            "arquivo_existe": os.path.exists(EXCEL_FILE),
            "total_registros": len(df) if not df.empty else 0,
            "colunas": list(df.columns) if not df.empty else []
        }
        
        if not df.empty:
            colunas = identificar_colunas(df)
            info.update(colunas)
            
            if 'descricao' in colunas:
                info["produtos_exemplo"] = df[colunas['descricao']].head(5).tolist()
            
            if 'valor' in colunas:
                info["valores_exemplo"] = df[colunas['valor']].head(5).tolist()
        
        return jsonify(info)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/testar-busca/<nome_produto>', methods=['GET'])
def testar_busca(nome_produto):
    """Endpoint para testar a busca de produtos"""
    try:
        produtos = buscar_produtos_por_nome(nome_produto)
        produtos_dict = [p.to_dict() for p in produtos]
        return jsonify({
            "produto_buscado": nome_produto,
            "resultados": produtos_dict
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/debug/busca', methods=['POST'])
def debug_busca():
    """Endpoint para debug da busca de produtos"""
    data = request.get_json()
    termo = data.get('termo', '')
    
    if not termo:
        return jsonify({"error": "Termo de busca não fornecido"}), 400
    
    try:
        # Buscar produtos
        produtos = buscar_produtos_por_nome(termo)
        produtos_dict = [p.to_dict() for p in produtos]
        
        # Analisar falha se não encontrou
        analise = None
        if not produtos:
            analise = analisar_falha_busca(termo)
        
        # Tentar processar com GLM
        glm_result = processar_intencao_com_glm(termo)
        
        return jsonify({
            "termo_busca": termo,
            "produtos_encontrados": produtos_dict,
            "analise_falha": analise,
            "glm_result": glm_result
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

@app.route('/testar-quantidade', methods=['POST'])
def testar_quantidade():
    """Endpoint para testar extração de quantidade"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Dados JSON inválidos"}), 400
    
    message = data.get('message', '')
    
    if not message:
        return jsonify({"error": "Mensagem não pode ser vazia"}), 400
    
    try:
        resultado = processar_intencao_com_glm(message)
        return jsonify({
            "mensagem_original": message,
            "resultado": resultado
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/testar-multiplicacao', methods=['POST'])
def testar_multiplicacao():
    """Endpoint para testar multiplicação"""
    data = request.get_json()
    message = data.get('message', '')
    
    # Testa extração
    quantidade = extrair_quantidade_da_mensagem(message)
    intent_data = processar_intencao_com_glm(message)
    
    # Testa busca
    produtos = buscar_produtos_por_nome(intent_data.get('produto', message))
    
    if produtos:
        produto = produtos[0]
        valor_unitario = float(produto.valor) if produto.valor else 0
        valor_total = valor_unitario * intent_data.get('quantidade', 1)
        
        return jsonify({
            "mensagem": message,
            "quantidade_extraida": quantidade,
            "intent_data": intent_data,
            "produto_encontrado": produto.descricao,
            "valor_unitario": valor_unitario,
            "valor_total": valor_total,
            "calculo": f"{intent_data.get('quantidade', 1)} × {valor_unitario} = {valor_total}"
        })
    else:
        return jsonify({"error": "Produto não encontrado"})


if __name__ == '__main__':
    print(" Iniciando servidor Flask...")
    print(f"Lendo do Excel: {EXCEL_FILE}")
    
    df = carregar_excel()
    if not df.empty:
        colunas = identificar_colunas(df)
        print(f" Pronto! {len(df)} produtos carregados")
        print(f" Colunas identificadas: {colunas}")
    else:
        print(" Problema ao carregar Excel")
    
    print("\n Endpoints:")
    print("   http://localhost:5001/ - Interface principal")
    print("   http://localhost:5001/chat - Chat principal")
    print("   http://localhost:5001/extract-products - Extrair produtos")
    print("   http://localhost:5001/admin/verificar-excel - Verificar Excel")
    print("   http://localhost:5001/testar-busca/PRODUTO - Testar busca")
    print("   http://localhost:5001/debug/busca - Debug de busca (POST)")
    
    app.run(debug=True, port=5001, host='0.0.0.0')